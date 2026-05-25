"""Textual widget: scrollable, clickable flowchart view."""

from __future__ import annotations

from textual import events
from textual.containers import ScrollableContainer
from textual.widgets import Static
from textual.message import Message
from textual.events import Click, MouseDown, MouseMove, MouseUp

from stag.tui.flowchart import ClickRegion, navigate_selection, render_flowchart


class FlowchartItemClicked(Message):
    """Posted when the user clicks a node or transition in the flowchart."""

    def __init__(self, kind: str, raw_id: str) -> None:
        super().__init__()
        self.kind = kind
        self.raw_id = raw_id


# Mouse-movement threshold (in chars) below which a press-release is treated as a click.
_DRAG_THRESHOLD = 2


class FlowchartView(ScrollableContainer, can_focus=True):
    """Scrollable, clickable, drag-pannable flowchart widget.

    Uses a ScrollableContainer + Static child so Textual handles scrollbars and
    wheel scrolling automatically. The Static child holds the rendered markup;
    its natural size drives the virtual content area.

    - mouse wheel / arrow keys: scroll
    - left-button drag: pan
    - left-button click (no drag): post FlowchartItemClicked on the hit region
    - 0 key (in app): recenter via recenter_to()
    """

    DEFAULT_CSS = """
    FlowchartView {
        background: $surface;
        scrollbar-size: 1 1;
    }
    FlowchartView > Static#flowchart-canvas {
        width: auto;
        height: auto;
    }
    """

    # Arrow key scrolling handled in on_key for reliability (BINDINGS dispatch
    # was not firing in practice — likely because ScrollableContainer or the
    # focused Static child intercepts the keys before the action runs).

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._canvas = Static("", id="flowchart-canvas", markup=True)
        self._handle = None
        self._center_node_id: str | None = None
        self._selected: tuple[str, str] | None = None
        self._depth: int = 2
        self._click_map: list[ClickRegion] = []
        self._drag_origin: tuple[int, int] | None = None
        self._drag_scroll_start: tuple[float, float] | None = None
        self._drag_moved: bool = False

    def compose(self):
        yield self._canvas

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self, handle, center_node_id: str, depth: int | None = None) -> None:
        """Load a run and render from center_node_id with center auto-selected."""
        self._handle = handle
        self._center_node_id = center_node_id
        self._selected = ("node", center_node_id)
        if depth is not None:
            self._depth = depth
        else:
            self._depth = self._auto_depth()
        self._refresh_lines()

    def set_selected(self, kind: str | None, raw_id: str | None) -> None:
        """Update the selection highlight without changing the center."""
        if kind is None or raw_id is None:
            self._selected = None
        else:
            self._selected = (kind, raw_id)
        self._refresh_lines()

    def adjust_depth(self, delta: int) -> None:
        self._depth = max(1, min(6, self._depth + delta))
        self._refresh_lines()

    def recenter_to(self, node_id: str | None = None) -> None:
        """Recenter the flowchart on node_id (or the current center) and scroll home."""
        if node_id is not None and node_id != self._center_node_id:
            self._center_node_id = node_id
            self._refresh_lines()
        self.scroll_home(animate=False)

    # Legacy alias used by app.py before this fix.
    def recenter(self) -> None:
        self.scroll_home(animate=False)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _auto_depth(self) -> int:
        h = self.size.height or 24
        from stag.tui.flowchart import BAND_H
        return max(1, min(4, (h // BAND_H) - 1))

    def _refresh_lines(self) -> None:
        if self._handle is None or self._center_node_id is None:
            return
        lines, regions = render_flowchart(
            self._handle, self._center_node_id, self._depth, selected=self._selected
        )
        self._click_map = regions
        self._canvas.update("\n".join(lines) if lines else " ")

    # ------------------------------------------------------------------
    # Mouse: drag-pan + click (mutually exclusive based on movement)
    # ------------------------------------------------------------------

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button != 1:
            return
        self._drag_origin = (event.screen_x, event.screen_y)
        self._drag_scroll_start = (self.scroll_x, self.scroll_y)
        self._drag_moved = False
        self.capture_mouse()
        self.focus()

    def on_mouse_move(self, event: MouseMove) -> None:
        if self._drag_origin is None:
            return
        dx = self._drag_origin[0] - event.screen_x
        dy = self._drag_origin[1] - event.screen_y
        if not self._drag_moved and abs(dx) + abs(dy) < _DRAG_THRESHOLD:
            return
        self._drag_moved = True
        sx, sy = self._drag_scroll_start or (0, 0)
        self.scroll_to(sx + dx, sy + dy, animate=False)

    def on_mouse_up(self, _event: MouseUp) -> None:
        self.release_mouse()
        self._drag_origin = None
        self._drag_scroll_start = None
        # _drag_moved cleared on next mouse_down; on_click checks it.

    def on_click(self, event: Click) -> None:
        # If the user dragged, suppress the click so we don't navigate accidentally.
        if self._drag_moved:
            self._drag_moved = False
            event.stop()
            return
        # Translate widget-relative click coordinates into content coordinates
        # by adding current scroll offset.
        content_x = event.x + int(self.scroll_x)
        content_y = event.y + int(self.scroll_y)
        for region in self._click_map:
            if region.row == content_y and region.col_start <= content_x <= region.col_end:
                self.post_message(FlowchartItemClicked(region.kind, region.raw_id))
                event.stop()
                return

    # ------------------------------------------------------------------
    # Keyboard scrolling
    # ------------------------------------------------------------------

    def navigate(self, direction: str) -> None:
        """Move the selection in the given direction and update detail / scroll.

        direction in {"up", "down", "left", "right"}.
        """
        if self._handle is None or self._center_node_id is None:
            return
        nxt = navigate_selection(
            self._handle, self._center_node_id, self._depth, self._selected, direction
        )
        if nxt is None:
            return
        self._selected = nxt
        self._refresh_lines()
        self._scroll_to_selection()
        self.post_message(FlowchartItemClicked(nxt[0], nxt[1]))

    def _scroll_to_selection(self) -> None:
        """Scroll so the currently selected item's row is visible."""
        if not self._selected or not self._click_map:
            return
        kind, rid = self._selected
        rows = [r.row for r in self._click_map if r.kind == kind and r.raw_id == rid]
        if not rows:
            return
        target_row = rows[len(rows) // 2]  # middle row of multi-row regions (e.g. node boxes)
        viewport_h = self.size.height or 20
        scroll_y = self.scroll_y
        # If above viewport, scroll up; if below, scroll down so it's centered-ish.
        if target_row < scroll_y + 2:
            self.scroll_to(self.scroll_x, max(0, target_row - 2), animate=False)
        elif target_row > scroll_y + viewport_h - 3:
            self.scroll_to(self.scroll_x, target_row - viewport_h + 3, animate=False)

