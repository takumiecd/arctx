"""Textual widget: scrollable, clickable flowchart view."""

from __future__ import annotations

from textual.message import Message
from textual.widget import Widget
from textual.events import Click, MouseDown, MouseMove, MouseUp

from stag.tui.flowchart import ClickRegion, render_flowchart


class FlowchartItemClicked(Message):
    """Posted when the user clicks a node or transition in the flowchart."""

    def __init__(self, kind: str, raw_id: str) -> None:
        super().__init__()
        self.kind = kind
        self.raw_id = raw_id


class FlowchartView(Widget):
    """Scrollable, clickable widget that renders the flowchart for a given center node.

    Renders Rich-markup lines via a scrollable Widget.
    Posts FlowchartItemClicked messages when the user clicks a node or transition.
    """

    DEFAULT_CSS = """
    FlowchartView {
        overflow: auto auto;
        background: $surface;
    }
    """

    _depth: int = 2
    _handle = None
    _center_node_id: str | None = None
    _drag_start: tuple[int, int] | None = None
    _drag_scroll_start: tuple[int, int] | None = None
    _lines: list[str] = []
    _click_map: list[ClickRegion] = []

    def show(self, handle, center_node_id: str, depth: int | None = None) -> None:
        self._handle = handle
        self._center_node_id = center_node_id
        if depth is not None:
            self._depth = depth
        else:
            self._depth = self._auto_depth()
        self._refresh_lines()

    def _auto_depth(self) -> int:
        """Estimate depth based on widget size. Cap at 4."""
        h = self.size.height or 24
        from stag.tui.flowchart import BAND_H
        return max(1, min(4, (h // BAND_H) - 1))

    def _refresh_lines(self) -> None:
        if self._handle is None or self._center_node_id is None:
            return
        lines, regions = render_flowchart(self._handle, self._center_node_id, self._depth)
        self._lines = lines
        self._click_map = regions
        self.refresh()

    def render(self) -> str:
        return "\n".join(self._lines) if self._lines else " "

    def adjust_depth(self, delta: int) -> None:
        self._depth = max(1, min(6, self._depth + delta))
        self._refresh_lines()

    def recenter(self) -> None:
        self.scroll_home(animate=False)

    # ------------------------------------------------------------------
    # Click handling
    # ------------------------------------------------------------------

    def on_click(self, event: Click) -> None:
        """Translate click coords to content coords and look up click map."""
        # event.x / event.y are relative to the widget's content origin
        # (already adjusted for scroll by Textual for content-area events).
        # We use scroll_offset to translate screen-relative → content-relative.
        content_x = event.x + int(self.scroll_x)
        content_y = event.y + int(self.scroll_y)

        for region in self._click_map:
            if region.row == content_y and region.col_start <= content_x <= region.col_end:
                self.post_message(FlowchartItemClicked(region.kind, region.raw_id))
                event.stop()
                return

    # ------------------------------------------------------------------
    # Drag-to-pan (preserved from original)
    # ------------------------------------------------------------------

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button == 1:
            self._drag_start = (event.screen_x, event.screen_y)
            self._drag_scroll_start = (self.scroll_x, self.scroll_y)
            self.capture_mouse()

    def on_mouse_move(self, event: MouseMove) -> None:
        if self._drag_start is None:
            return
        dx = self._drag_start[0] - event.screen_x
        dy = self._drag_start[1] - event.screen_y
        sx, sy = self._drag_scroll_start or (0, 0)
        self.scroll_to(sx + dx, sy + dy, animate=False)

    def on_mouse_up(self, _event: MouseUp) -> None:
        self._drag_start = None
        self._drag_scroll_start = None
        self.release_mouse()
