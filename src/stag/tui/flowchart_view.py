"""Textual widget: scrollable, drag-pannable flowchart view."""

from __future__ import annotations

from textual.widget import Widget
from textual.events import MouseDown, MouseMove, MouseUp

from stag.tui.flowchart import render_flowchart


class FlowchartView(Widget):
    """Scrollable widget that renders the flowchart for a given center node.

    Renders Rich-markup lines via a scrollable Widget.
    """

    DEFAULT_CSS = """
    FlowchartView {
        overflow: auto auto;
    }
    """

    _depth: int = 2
    _handle = None
    _center_node_id: str | None = None
    _drag_start: tuple[int, int] | None = None
    _drag_scroll_start: tuple[int, int] | None = None
    _lines: list[str] = []

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
        self._lines = render_flowchart(self._handle, self._center_node_id, self._depth)
        self.refresh()

    def render(self) -> str:
        return "\n".join(self._lines) if self._lines else " "

    def adjust_depth(self, delta: int) -> None:
        self._depth = max(1, min(6, self._depth + delta))
        self._refresh_lines()

    def recenter(self) -> None:
        self.scroll_home(animate=False)

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
