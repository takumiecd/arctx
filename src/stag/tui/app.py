"""STAG TUI — 3-pane Textual app (Runs | Flowchart | Detail)."""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Label, ListItem, ListView, Markdown

from stag.tui.detail import build_detail_markdown
from stag.tui.flowchart_view import FlowchartItemClicked, FlowchartView
from stag.tui.graph_html import render_graph_html


class StagApp(App):
    """STAG Textual UI — runs list, flowchart, detail panes."""

    CSS_PATH = Path(__file__).parent / "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "focus_runs", "Runs"),
        Binding("2", "focus_flowchart", "Flowchart"),
        Binding("3", "focus_detail", "Detail"),
        Binding("g", "open_browser_graph", "Graph"),
        Binding("+", "depth_increase", "+Depth"),
        Binding("-", "depth_decrease", "-Depth"),
        Binding("0", "recenter_flowchart", "Recenter"),
        # Arrow keys scroll the flowchart unless the focused widget overrides
        # them (e.g. ListView already binds up/down for cursor movement).
        Binding("up", "flowchart_scroll('up')", show=False),
        Binding("down", "flowchart_scroll('down')", show=False),
        Binding("left", "flowchart_scroll('left')", show=False),
        Binding("right", "flowchart_scroll('right')", show=False),
    ]

    def __init__(self, store, **kwargs):
        super().__init__(**kwargs)
        self._store = store
        self._current_handle = None
        self._state_labels: dict[str, str] = {}
        self._plan_labels: dict[str, str] = {}
        self._selected: tuple[str, str] | None = None  # (kind, raw_id)
        self._runs_meta: list[dict] = []

    def compose(self) -> ComposeResult:
        # Sidebar.
        with Container(id="sidebar"):
            yield Label("Runs", id="sidebar-title")
            yield ListView(id="runs-list")

        # Flowchart pane (central).
        with Container(id="flowchart-pane"):
            yield Label("Flowchart", id="flowchart-pane-title")
            yield FlowchartView(id="flowchart-view")

        # Detail pane.
        with Container(id="detail-pane"):
            yield Label("Detail", id="detail-pane-title")
            yield Markdown("", id="detail-markdown")

        yield Footer()

    def on_mount(self) -> None:
        self._load_runs()

    # ------------------------------------------------------------------
    # Runs list
    # ------------------------------------------------------------------

    def _load_runs(self) -> None:
        runs = self._store.list_runs()
        self._runs_meta = runs
        lv = self.query_one("#runs-list", ListView)
        lv.clear()
        for meta in runs:
            rid = meta["run_id"]
            lv.append(ListItem(Label(rid), name=rid))
        # Auto-select first run if present.
        if runs and self._current_handle is None:
            first_id = runs[0]["run_id"]
            try:
                handle = self._store.load_run(first_id)
                self._current_handle = handle
                self._load_run(handle)
            except Exception:
                pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "runs-list":
            return
        self._load_run_from_item(event.item)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "runs-list":
            return
        if event.item is not None:
            self._load_run_from_item(event.item)

    def _load_run_from_item(self, item) -> None:
        run_id = item.name
        if not run_id:
            return
        if self._current_handle is not None and self._current_handle.run_id == run_id:
            return
        try:
            handle = self._store.load_run(run_id)
        except Exception as exc:
            self._set_markdown(f"# Error\n\nFailed to load run: {exc}")
            return
        self._current_handle = handle
        self._load_run(handle)

    def _load_run(self, handle) -> None:
        """Initialize flowchart and detail for a freshly loaded run."""
        from stag.tui.flowchart import _build_labels
        state_labels, plan_labels = _build_labels(handle)
        self._state_labels = state_labels
        self._plan_labels = plan_labels
        self._selected = None

        fv = self.query_one("#flowchart-view", FlowchartView)
        fv.show(handle, handle.root_node_id)

        self._set_markdown(build_detail_markdown(handle, None, state_labels, plan_labels))

    # ------------------------------------------------------------------
    # Flowchart click handler
    # ------------------------------------------------------------------

    def on_flowchart_item_clicked(self, event: FlowchartItemClicked) -> None:
        if self._current_handle is None:
            return
        self._selected = (event.kind, event.raw_id)

        node_data = {"type": event.kind, "id": event.raw_id}
        md = build_detail_markdown(
            self._current_handle,
            node_data,
            self._state_labels,
            self._plan_labels,
        )
        self._set_markdown(md)

        fv = self.query_one("#flowchart-view", FlowchartView)
        # Keep the center stable on all clicks; just update selection highlight.
        fv.set_selected(event.kind, event.raw_id)

    # ------------------------------------------------------------------
    # Detail pane helpers
    # ------------------------------------------------------------------

    def _set_markdown(self, text: str) -> None:
        md = self.query_one("#detail-markdown", Markdown)
        md.update(text)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self._load_runs()
        if self._current_handle is not None:
            try:
                handle = self._store.load_run(self._current_handle.run_id)
                self._current_handle = handle
                self._load_run(handle)
            except Exception:
                pass

    def action_focus_runs(self) -> None:
        self.query_one("#runs-list").focus()

    def action_focus_flowchart(self) -> None:
        self.query_one("#flowchart-view").focus()

    def action_focus_detail(self) -> None:
        self.query_one("#detail-markdown").focus()

    def action_open_browser_graph(self) -> None:
        if self._current_handle is None:
            return
        html = render_graph_html(self._current_handle)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = f.name
        webbrowser.open(f"file://{path}")

    def action_depth_increase(self) -> None:
        self.query_one("#flowchart-view", FlowchartView).adjust_depth(1)

    def action_depth_decrease(self) -> None:
        self.query_one("#flowchart-view", FlowchartView).adjust_depth(-1)

    def action_flowchart_scroll(self, direction: str) -> None:
        fv = self.query_one("#flowchart-view", FlowchartView)
        fv.navigate(direction)

    def action_recenter_flowchart(self) -> None:
        if self._current_handle is None:
            return
        fv = self.query_one("#flowchart-view", FlowchartView)
        # Recenter on the currently selected node, or fall back to root.
        selected = self._selected
        if selected is not None and selected[0] == "node":
            target_node_id = selected[1]
        else:
            target_node_id = self._current_handle.root_node_id
        fv.recenter_to(target_node_id)
