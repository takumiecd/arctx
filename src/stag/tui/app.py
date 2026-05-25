"""STAG TUI — 3-pane Textual app."""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer
from textual.widgets import Footer, Label, ListItem, ListView, Markdown, Static, Tree

from stag.tui.dag_tree import populate_dag_tree
from stag.tui.detail import build_detail_markdown
from stag.tui.flowchart_view import FlowchartView
from stag.tui.graph_html import render_graph_html


class StagApp(App):
    """STAG Textual UI — runs list, DAG tree, detail/flowchart panes."""

    CSS_PATH = Path(__file__).parent / "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "focus_runs", "Runs"),
        Binding("2", "focus_tree", "Tree"),
        Binding("3", "focus_detail", "Detail"),
        Binding("m", "toggle_flowchart", "Flowchart", priority=True),
        Binding("g", "open_browser_graph", "Graph"),
        Binding("+", "depth_increase", "+Depth"),
        Binding("-", "depth_decrease", "-Depth"),
        Binding("0", "recenter_flowchart", "Recenter"),
        Binding("e", "expand_all", "Expand all"),
        Binding("c", "collapse_all", "Collapse all"),
    ]

    def __init__(self, store, **kwargs):
        super().__init__(**kwargs)
        self._store = store
        self._current_handle = None
        self._state_labels: dict[str, str] = {}
        self._plan_labels: dict[str, str] = {}
        self._flowchart_mode = False
        self._current_node_data: dict | None = None
        self._runs_meta: list[dict] = []

    def compose(self) -> ComposeResult:
        # Sidebar.
        with Container(id="sidebar"):
            yield Label("Runs", id="sidebar-title")
            yield ListView(id="runs-list")

        # DAG tree pane.
        with Container(id="dag-pane"):
            yield Label("DAG Tree", id="dag-pane-title")
            yield Tree("(no run)", id="dag-tree")

        # Detail pane.
        with Container(id="detail-pane"):
            yield Label("Detail", id="detail-pane-title")
            yield Markdown("", id="detail-markdown")
            yield FlowchartView(id="flowchart-view")

        yield Footer()

    def on_mount(self) -> None:
        # Ensure flowchart is hidden and markdown is visible initially,
        # regardless of CSS load order.
        self.query_one("#flowchart-view").display = False
        self.query_one("#detail-markdown").display = True
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
            label = rid
            lv.append(ListItem(Label(label), name=rid))
        # Auto-select first run if present.
        if runs and self._current_handle is None:
            first_id = runs[0]["run_id"]
            try:
                handle = self._store.load_run(first_id)
                self._current_handle = handle
                self._populate_tree(handle)
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
        self._populate_tree(handle)

    # ------------------------------------------------------------------
    # DAG tree
    # ------------------------------------------------------------------

    def _populate_tree(self, handle) -> None:
        tree = self.query_one("#dag-tree", Tree)
        tree.root.label = handle.run_id
        state_labels, plan_labels = populate_dag_tree(tree, handle)
        self._state_labels = state_labels
        self._plan_labels = plan_labels
        tree.root.expand()
        self._set_markdown(build_detail_markdown(handle, None, state_labels, plan_labels))

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        if self._current_handle is None:
            return
        node_data = event.node.data
        self._current_node_data = node_data
        md = build_detail_markdown(
            self._current_handle,
            node_data,
            self._state_labels,
            self._plan_labels,
        )
        if self._flowchart_mode:
            center_id = self._resolve_center_node(node_data)
            fv = self.query_one("#flowchart-view", FlowchartView)
            fv.show(self._current_handle, center_id)
        else:
            self._set_markdown(md)

    # ------------------------------------------------------------------
    # Detail pane helpers
    # ------------------------------------------------------------------

    def _set_markdown(self, text: str) -> None:
        md = self.query_one("#detail-markdown", Markdown)
        md.update(text)

    def _resolve_center_node(self, node_data: dict | None) -> str:
        """Derive the center node_id for flowchart from tree selection."""
        if not node_data or self._current_handle is None:
            return self._current_handle.root_node_id if self._current_handle else ""
        kind = node_data.get("type", "")
        raw_id = node_data.get("id", "")
        graph = self._current_handle.run_graph

        if kind in ("node", "note"):
            if raw_id in graph.nodes:
                return raw_id
        if kind == "transition":
            inputs = graph.transition_inputs(raw_id)
            if inputs:
                return inputs[0]
        if kind == "backref":
            if raw_id in graph.nodes:
                return raw_id
            inputs = graph.transition_inputs(raw_id)
            if inputs:
                return inputs[0]
        if kind == "forward_pointer":
            inputs = graph.transition_inputs(raw_id)
            if inputs:
                return inputs[0]
        return self._current_handle.root_node_id

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self._load_runs()
        if self._current_handle is not None:
            try:
                handle = self._store.load_run(self._current_handle.run_id)
                self._current_handle = handle
                self._populate_tree(handle)
            except Exception:
                pass

    def action_focus_runs(self) -> None:
        self.query_one("#runs-list").focus()

    def action_focus_tree(self) -> None:
        self.query_one("#dag-tree").focus()

    def action_focus_detail(self) -> None:
        if self._flowchart_mode:
            self.query_one("#flowchart-view").focus()
        else:
            self.query_one("#detail-markdown").focus()

    def action_toggle_flowchart(self) -> None:
        self._flowchart_mode = not self._flowchart_mode
        md = self.query_one("#detail-markdown", Markdown)
        fv = self.query_one("#flowchart-view", FlowchartView)
        if self._flowchart_mode:
            md.display = False
            fv.display = True
            if self._current_handle is not None:
                center_id = self._resolve_center_node(self._current_node_data)
                fv.show(self._current_handle, center_id)
        else:
            fv.display = False
            md.display = True

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
        if self._flowchart_mode:
            self.query_one("#flowchart-view", FlowchartView).adjust_depth(1)

    def action_depth_decrease(self) -> None:
        if self._flowchart_mode:
            self.query_one("#flowchart-view", FlowchartView).adjust_depth(-1)

    def action_recenter_flowchart(self) -> None:
        if self._flowchart_mode:
            self.query_one("#flowchart-view", FlowchartView).recenter()

    def action_expand_all(self) -> None:
        tree = self.query_one("#dag-tree", Tree)
        tree.root.expand_all()

    def action_collapse_all(self) -> None:
        tree = self.query_one("#dag-tree", Tree)
        tree.root.collapse_all()
