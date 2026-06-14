"""ARCTX TUI — 3-pane Textual app (Runs | Flowchart | Detail)."""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Label, ListItem, ListView, Markdown

from arctx.payload_builder import build_payload
from arctx_tui.detail import build_detail_markdown
from arctx_tui.editor import (
    GitPayloadForm,
    GitPayloadFormData,
    PayloadForm,
    PayloadFormData,
    TransitionForm,
    TransitionFormData,
)
from arctx_tui.flowchart_view import FlowchartItemClicked, FlowchartView
from arctx_tui.graph_html import render_graph_html


class ArctxApp(App):
    """ARCTX Textual UI — runs list, flowchart, detail panes."""

    CSS_PATH = Path(__file__).parent / "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "focus_runs", "Runs"),
        Binding("2", "focus_flowchart", "Flowchart"),
        Binding("3", "focus_detail", "Detail"),
        Binding("g", "open_browser_graph", "Graph"),
        Binding("t", "create_transition", "Transition"),
        Binding("p", "attach_payload", "Payload"),
        Binding("c", "cut_selected", "Cut"),
        Binding("G", "attach_git_payload", "Git Payload"),
        Binding("+", "depth_increase", "+Depth"),
        Binding("-", "depth_decrease", "-Depth"),
        Binding("0", "recenter_flowchart", "Recenter"),
    ]

    def __init__(self, store, watch_interval: float | None = 2.0, **kwargs):
        super().__init__(**kwargs)
        self._store = store
        self._watch_interval = watch_interval
        self._current_handle = None
        self._state_labels: dict[str, str] = {}
        self._plan_labels: dict[str, str] = {}
        self._selected: tuple[str, str] | None = None  # (kind, raw_id)
        self._runs_meta: list[dict] = []
        self._run_signatures: dict[str, tuple[tuple[str, int, int], ...]] = {}

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
        if self._watch_interval is not None and self._watch_interval > 0:
            self.set_interval(self._watch_interval, self._refresh_if_changed)

    # ------------------------------------------------------------------
    # Runs list
    # ------------------------------------------------------------------

    def _load_runs(self) -> None:
        runs = self._store.list_runs()
        self._runs_meta = runs
        for meta in runs:
            rid = meta["run_id"]
            self._run_signatures.setdefault(rid, self._run_signature(rid))
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
                self._remember_run_signature(first_id)
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
        self._remember_run_signature(run_id)

    def _load_run(self, handle) -> None:
        """Initialize flowchart and detail for a freshly loaded run."""
        from arctx_tui.flowchart import _build_labels
        state_labels, plan_labels = _build_labels(handle)
        self._state_labels = state_labels
        self._plan_labels = plan_labels
        self._selected = None

        fv = self.query_one("#flowchart-view", FlowchartView)
        fv.show(handle, handle.root_node_id)

        self._set_markdown(build_detail_markdown(handle, None, state_labels, plan_labels))

    def _reload_current_run(self, *, selected: tuple[str, str] | None = None) -> None:
        if self._current_handle is None:
            return
        handle = self._store.load_run(self._current_handle.run_id)
        self._current_handle = handle
        self._load_run(handle)
        if selected is not None:
            self._select_item(*selected)
        self._remember_run_signature(handle.run_id)

    def _refresh_if_changed(self) -> None:
        """Reload list/current run when another writer changes the store."""
        try:
            pulled_records = self._pull_current_sync_updates()
        except Exception as exc:
            self.notify(f"Sync pull failed: {exc}", severity="error")
            pulled_records = 0
        changed_runs = self._changed_run_ids()
        if not changed_runs:
            return

        self._load_runs()
        if self._current_handle is None:
            return
        run_id = self._current_handle.run_id
        if run_id not in changed_runs:
            return

        selected = self._selected
        try:
            self._reload_current_run(selected=selected)
        except Exception as exc:
            self.notify(f"Refresh failed: {exc}", severity="error")
            return
        if pulled_records:
            self.notify(f"Pulled {pulled_records} shared records into {run_id}")
        else:
            self.notify(f"Updated run {run_id}")

    def _pull_current_sync_updates(self) -> int:
        if self._current_handle is None:
            return 0
        try:
            from arctx.core.sync import local as sync

            run_path = self._store.run_path(self._current_handle.run_id)
            cfg = sync.load_sync_config(run_path)
            result = sync.sync_pull(
                handle=self._current_handle,
                remote=cfg["remote"],
                shared_run_id=cfg["shared_run_id"],
                remote_dir=cfg["remote_dir"],
            )
            pulled_records = int(result.get("pulled_records") or 0)
            if pulled_records:
                self._store.save_run(self._current_handle)
            return pulled_records
        except RuntimeError as exc:
            if "sync is not initialized" in str(exc):
                return 0
            raise
        except FileNotFoundError:
            return 0
        except KeyError:
            return 0

    def _changed_run_ids(self) -> set[str]:
        current = {
            meta["run_id"]: self._run_signature(meta["run_id"])
            for meta in self._store.list_runs()
        }
        changed = {
            run_id
            for run_id, signature in current.items()
            if self._run_signatures.get(run_id) != signature
        }
        removed = set(self._run_signatures) - set(current)
        self._run_signatures = current
        return changed | removed

    def _remember_run_signature(self, run_id: str) -> None:
        self._run_signatures[run_id] = self._run_signature(run_id)

    def _run_signature(self, run_id: str) -> tuple[tuple[str, int, int], ...]:
        run_path = self._store.run_path(run_id)
        if not run_path.exists():
            return ()
        files = (
            "run.json",
            "graph.json",
            "nodes.jsonl",
            "transitions.jsonl",
            "payloads.jsonl",
            "work_sessions.jsonl",
            "work_events.jsonl",
            "run.db",
        )
        signature: list[tuple[str, int, int]] = []
        for name in files:
            path = run_path / name
            if not path.exists():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            signature.append((name, stat.st_size, stat.st_mtime_ns))
        return tuple(signature)

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

    def _select_item(self, kind: str, raw_id: str) -> None:
        if self._current_handle is None:
            return
        self._selected = (kind, raw_id)

        node_data = {"type": kind, "id": raw_id}
        md = build_detail_markdown(
            self._current_handle,
            node_data,
            self._state_labels,
            self._plan_labels,
        )
        self._set_markdown(md)

        fv = self.query_one("#flowchart-view", FlowchartView)
        fv.set_selected(kind, raw_id)

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

    def action_create_transition(self) -> None:
        if self._current_handle is None:
            return
        selected = self._selected
        if selected is None:
            node_id = self._current_handle.root_node_id
        elif selected[0] == "node":
            node_id = selected[1]
        else:
            node_id = self._current_handle.run_graph.transition_output(selected[1])
        if not node_id:
            return
        self.push_screen(TransitionForm(default_node_id=node_id), self._create_transition)

    def _create_transition(self, data: TransitionFormData | None) -> None:
        if self._current_handle is None or data is None:
            return
        try:
            field_data = {"type": data.payload_kind, **data.content}
            payload = build_payload(
                payload_type=data.payload_type,
                target_kind="transition",
                target_id="pending",
                payload_id="pending",
                field_data=field_data,
            )
            transition = self._current_handle.transition(list(data.input_node_ids), payload)
            self._store.save_run(self._current_handle)
            self._reload_current_run(selected=("transition", transition.transition_id))
            self.notify(f"Created transition {transition.transition_id}")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_attach_payload(self) -> None:
        if self._current_handle is None or self._selected is None:
            self.notify("Select a node or transition first", severity="warning")
            return
        kind, raw_id = self._selected
        if kind not in ("node", "transition"):
            return
        self.push_screen(PayloadForm(target_kind=kind, target_id=raw_id), self._attach_payload)

    def _attach_payload(self, data: PayloadFormData | None) -> None:
        if self._current_handle is None or data is None:
            return
        try:
            field_data = {"type": data.payload_kind, **data.content}
            payload = build_payload(
                payload_type=data.payload_type,
                target_kind=data.target_kind,
                target_id=data.target_id,
                payload_id=(
                    "pending"
                    if data.target_kind == "node"
                    else self._current_handle._next_id("pl")
                ),
                field_data=field_data,
            )
            if data.target_kind == "node":
                attached = self._current_handle.attach(data.target_id, payload)
            else:
                self._current_handle.run_graph.attach_payload(payload)
                attached = payload
            self._store.save_run(self._current_handle)
            self._reload_current_run(selected=(data.target_kind, data.target_id))
            self.notify(f"Attached payload {attached.payload_id}")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_cut_selected(self) -> None:
        if self._current_handle is None or self._selected is None:
            self.notify("Select a node or transition first", severity="warning")
            return
        kind, raw_id = self._selected
        if kind not in ("node", "transition"):
            return
        try:
            cut = self._current_handle.cut(raw_id, target_kind=kind)
            self._store.save_run(self._current_handle)
            self._reload_current_run(selected=(kind, raw_id))
            self.notify(f"Cut {kind} {raw_id} with {cut.payload_id}")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_attach_git_payload(self) -> None:
        if self._current_handle is None or self._selected is None:
            self.notify("Select a transition first", severity="warning")
            return
        kind, raw_id = self._selected
        if kind != "transition":
            self.notify("Git payloads attach to transitions", severity="warning")
            return
        self.push_screen(GitPayloadForm(transition_id=raw_id), self._attach_git_payload)

    def _attach_git_payload(self, data: GitPayloadFormData | None) -> None:
        if self._current_handle is None or data is None:
            return
        try:
            from arctx.ext.git.helpers.attach import attach_commits_to_transition

            result = attach_commits_to_transition(
                self._current_handle,
                self._store.run_path(self._current_handle.run_id),
                data.transition_id,
                data.commits,
            )
            self._store.save_run(self._current_handle)
            self._reload_current_run(selected=("transition", data.transition_id))
            payload_id = result["created"]["git_change_payload_id"]
            self.notify(f"Attached git payload {payload_id}")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_depth_increase(self) -> None:
        self.query_one("#flowchart-view", FlowchartView).adjust_depth(1)

    def action_depth_decrease(self) -> None:
        self.query_one("#flowchart-view", FlowchartView).adjust_depth(-1)

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
