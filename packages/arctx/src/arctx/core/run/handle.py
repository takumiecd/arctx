"""Run handle definition and initialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from arctx.core.cuts import is_active_node
from arctx.core.ids import opaque_id, slugify, timestamp_id
from arctx.core.run_graph import RunGraph
from arctx.core.schema.graph import Node
from arctx.core.schema.requirements import Requirement
from arctx.core.schema.work import Lane, WorkEvent
from arctx.core.types import JSONValue


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
                "no new steps can extend it"
            )

    def save(self, store) -> object:
        return store.save_run(self)

    def ensure_lane(
        self,
        *,
        name: str | None = None,
        lane_id: str | None = None,
        user_id: str | None = None,
        created_by: str | None = None,
        parent_lane_id: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> Lane:
        """Create or return a Lane — a solo-or-collaborative append-only unit.

        A lane is not owned by one user: ``user_id`` only records who opened
        it, and any actor may later append events to the same lane (attribution
        is per :class:`WorkEvent`). ``lane_id`` defaults to a fresh opaque id.
        """
        lid = lane_id or opaque_id("lane")
        existing = self.run_graph.lanes.get(lid)
        if existing is not None:
            return existing
        lane = Lane(
            lane_id=lid,
            run_id=self.run_id,
            created_by=user_id or created_by or "",
            parent_lane_id=parent_lane_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
            name=name,
        )
        self.run_graph.add_lane(lane)
        return lane

    def record_work_event(
        self,
        *,
        user_id: str | None,
        lane_id: str | None = None,
        event_type: str,
        target_kind: str | None = None,
        target_id: str | None = None,
        created_records: tuple[str, ...] = (),
        summary: str | None = None,
        data: dict[str, JSONValue] | None = None,
    ) -> WorkEvent | None:
        lid = lane_id
        if user_id is None or lid is None:
            return None
        self.ensure_lane(user_id=user_id, lane_id=lid)
        event = WorkEvent(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            lane_id=lid,
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
    """Create a new in-memory run with a seeded root Node."""

    rid = run_id or timestamp_id(f"run_{slugify(requirement.requirement_id)}")

    graph = RunGraph()
    root = Node(node_id=opaque_id("n"))
    graph.add_node(root)
    graph.metadata["root_node_id"] = root.node_id

    handle = RunHandle(
        run_id=rid,
        requirement=requirement,
        run_graph=graph,
        _counters={},
    )
    return handle


# Bind verb implementations.
from arctx.core.run.asset import attach_asset_impl as _attach_asset_impl  # noqa: E402
from arctx.core.run.attach import attach_impl as _attach_impl  # noqa: E402
from arctx.core.run.cut import cut_impl as _cut_impl  # noqa: E402
from arctx.core.run.uncut import uncut_impl as _uncut_impl  # noqa: E402
from arctx.core.run.lane import adopt_lane_records_impl as _adopt_lane_records_impl  # noqa: E402
from arctx.core.run.outcomes import outcomes_impl as _outcomes_impl  # noqa: E402
from arctx.core.run.trace import trace_impl as _trace_impl  # noqa: E402
from arctx.core.run.step import add_step_impl as _add_step_impl  # noqa: E402
from arctx.core.run.reparent import reparent_impl as _reparent_impl  # noqa: E402

RunHandle.add_step = _add_step_impl
RunHandle.attach = _attach_impl
RunHandle.attach_asset = _attach_asset_impl
RunHandle.cut = _cut_impl
RunHandle.uncut = _uncut_impl
RunHandle.reparent = _reparent_impl
RunHandle.adopt_lane_records = _adopt_lane_records_impl
RunHandle.trace = _trace_impl
RunHandle.history = _trace_impl
RunHandle.outcomes = _outcomes_impl
