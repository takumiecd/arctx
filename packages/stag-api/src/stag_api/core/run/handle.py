"""Run handle definition and initialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from stag_api.core.cuts import is_active_node
from stag_api.core.graph_view import GraphView
from stag_api.core.ids import opaque_id, slugify, timestamp_id
from stag_api.core.run_graph import RunGraph
from stag_api.core.schema.graph import Node
from stag_api.core.schema.requirements import Requirement
from stag_api.core.schema.work import WorkEvent, WorkSession
from stag_api.core.types import JSONValue


@dataclass
class RunHandle:
    """In-memory handle for one optimization/problem-solving run."""

    run_id: str
    requirement: Requirement
    run_graph: RunGraph
    _counters: dict[str, int] = field(default_factory=dict)

    def _next_id(self, prefix: str) -> str:
        return opaque_id(prefix)

    @property
    def root_node_id(self) -> str:
        root = self.run_graph.metadata.get("root_node_id")
        if root is not None:
            return str(root)
        roots = self.run_graph.roots()
        if roots:
            return roots[0]
        return "n_0000"

    def _ensure_active_node(self, node_id: str) -> None:
        """Reject node IDs that are unknown or sit inside a cut subtree."""
        if node_id not in self.run_graph.nodes:
            raise KeyError(f"unknown node_id: {node_id}")
        if not is_active_node(self.run_graph, node_id):
            raise ValueError(
                f"node is in a cut (inactive) branch: {node_id}; "
                "no new transitions can extend it"
            )

    def _get_view(self, name: str) -> GraphView:
        if name not in self.run_graph.views:
            raise KeyError(f"unknown view: {name!r}")
        return self.run_graph.views[name]

    def save(self, store) -> object:
        return store.save_run(self)

    def ensure_work_session(
        self,
        *,
        user_id: str | None,
        work_session_id: str | None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> WorkSession | None:
        if user_id is None or work_session_id is None:
            return None
        existing = self.run_graph.work_sessions.get(work_session_id)
        if existing is not None:
            if existing.user_id != user_id:
                raise ValueError(
                    f"work_session_id {work_session_id!r} belongs to "
                    f"user {existing.user_id!r}, not {user_id!r}"
                )
            return existing
        session = WorkSession(
            work_session_id=work_session_id,
            run_id=self.run_id,
            user_id=user_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
        )
        self.run_graph.add_work_session(session)
        return session

    def record_work_event(
        self,
        *,
        user_id: str | None,
        work_session_id: str | None,
        event_type: str,
        target_kind: str | None = None,
        target_id: str | None = None,
        created_records: tuple[str, ...] = (),
        summary: str | None = None,
        data: dict[str, JSONValue] | None = None,
    ) -> WorkEvent | None:
        if user_id is None or work_session_id is None:
            return None
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)
        event = WorkEvent(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            event_type=event_type,
            target_kind=target_kind,
            target_id=target_id,
            created_records=tuple(created_records),
            summary=summary,
            data=dict(data or {}),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.run_graph.add_work_event(event)
        return event


def init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle:
    """Create a new in-memory run with a seeded RunGraph and 'main' GraphView."""

    rid = run_id or timestamp_id(f"run_{slugify(requirement.requirement_id)}")

    graph = RunGraph()
    root = Node(node_id=opaque_id("n"))
    graph.add_node(root)
    graph.metadata["root_node_id"] = root.node_id

    main_view = GraphView(
        view_id=opaque_id("view"),
        name="main",
        root_node_id=root.node_id,
    )
    graph.add_view(main_view)

    handle = RunHandle(
        run_id=rid,
        requirement=requirement,
        run_graph=graph,
        _counters={},
    )
    return handle


# Bind verb implementations.
from stag_api.core.run.anchor import anchor_impl as _anchor_impl  # noqa: E402
from stag_api.core.run.attach import attach_impl as _attach_impl  # noqa: E402
from stag_api.core.run.cut import cut_impl as _cut_impl  # noqa: E402
from stag_api.core.run.outcomes import outcomes_impl as _outcomes_impl  # noqa: E402
from stag_api.core.run.trace import trace_impl as _trace_impl  # noqa: E402
from stag_api.core.run.transition import transition_impl as _transition_impl  # noqa: E402
from stag_api.core.run.view import view_create_impl as _view_create_impl  # noqa: E402
from stag_api.core.run.view import view_list_impl as _view_list_impl  # noqa: E402
from stag_api.core.run.view import view_show_impl as _view_show_impl  # noqa: E402

RunHandle.transition = _transition_impl
RunHandle.attach = _attach_impl
RunHandle.anchor = _anchor_impl
RunHandle.cut = _cut_impl
RunHandle.trace = _trace_impl
RunHandle.history = _trace_impl
RunHandle.outcomes = _outcomes_impl
RunHandle.view_create = _view_create_impl
RunHandle.view_list = _view_list_impl
RunHandle.view_show = _view_show_impl
