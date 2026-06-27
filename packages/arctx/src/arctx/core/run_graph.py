"""Single global DAG container for a run."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from arctx.core.schema.graph import Node, Step
from arctx.core.schema.payloads import PayloadBase
from arctx.core.schema.work import Lane, WorkEvent
from arctx.core.types import JSONValue, to_jsonable


@dataclass
class RunGraph:
    """Append-only graph records for one run."""

    nodes: dict[str, Node] = field(default_factory=dict)
    steps: dict[str, Step] = field(default_factory=dict)
    payloads: dict[str, PayloadBase] = field(default_factory=dict)
    lanes: dict[str, Lane] = field(default_factory=dict)
    work_events: list[WorkEvent] = field(default_factory=list)

    # Reverse-lookup indices (not persisted; rebuilt on load).
    steps_by_input_node: dict[str, list[str]] = field(default_factory=dict)
    # A node may be the output of multiple steps (append-only re-parent), but at
    # most one of them is active at a time. The list preserves insertion order.
    step_by_output_node: dict[str, list[str]] = field(default_factory=dict)
    payloads_by_node: dict[str, list[str]] = field(default_factory=dict)
    payloads_by_step: dict[str, list[str]] = field(default_factory=dict)

    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def add_lane(self, lane: Lane) -> None:
        if lane.lane_id in self.lanes:
            existing = self.lanes[lane.lane_id]
            if existing.created_by != lane.created_by:
                raise ValueError(
                    f"lane_id {lane.lane_id!r} belongs to "
                    f"user {existing.created_by!r}, not {lane.created_by!r}"
                )
            return
        self.lanes[lane.lane_id] = lane

    def add_work_event(self, event: WorkEvent) -> None:
        if event.lane_id not in self.lanes:
            raise KeyError(f"unknown lane_id: {event.lane_id}")
        if any(existing.event_id == event.event_id for existing in self.work_events):
            raise ValueError(f"duplicate work_event_id: {event.event_id}")
        self.work_events.append(event)

    # ----- mutations -------------------------------------------------------

    def add_node(self, node: Node) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_step(self, step: Step) -> None:
        if step.step_id in self.steps:
            raise ValueError(f"duplicate step_id: {step.step_id}")
        # Validate output node exists.
        if step.output_node_id and step.output_node_id not in self.nodes:
            raise KeyError(f"unknown output_node_id: {step.output_node_id}")
        # Validate each input node exists.
        for nid in step.input_node_ids:
            if nid not in self.nodes:
                raise KeyError(f"unknown input_node_id: {nid}")
        # A node may have multiple producing steps (append-only re-parent). The
        # "at most one active producer" policy is enforced by the write verbs,
        # not by this structural append.
        if step.output_node_id:
            producers = self.step_by_output_node.setdefault(step.output_node_id, [])
            if step.step_id not in producers:
                producers.append(step.step_id)
        for nid in step.input_node_ids:
            self.steps_by_input_node.setdefault(nid, []).append(step.step_id)
        self.steps[step.step_id] = step

    def attach_payload(self, payload: PayloadBase) -> None:
        if payload.payload_id in self.payloads:
            raise ValueError(f"duplicate payload_id: {payload.payload_id}")
        if payload.target_kind == "node":
            if payload.target_id not in self.nodes:
                raise KeyError(f"unknown target node: {payload.target_id}")
            self.payloads_by_node.setdefault(payload.target_id, []).append(payload.payload_id)
        elif payload.target_kind == "step":
            if payload.target_id not in self.steps:
                raise KeyError(f"unknown target step: {payload.target_id}")
            self.payloads_by_step.setdefault(payload.target_id, []).append(payload.payload_id)
        else:
            raise ValueError(f"unknown target_kind: {payload.target_kind!r}")
        self.payloads[payload.payload_id] = payload

    # ----- lookup ----------------------------------------------------------

    def steps_from_node(self, node_id: str) -> list[str]:
        return list(self.steps_by_input_node.get(node_id, ()))

    def producers_of(self, node_id: str) -> list[str]:
        """All steps whose output is *node_id* (active or not), in insertion order."""
        return list(self.step_by_output_node.get(node_id, ()))

    def step_to_node(self, node_id: str) -> str | None:
        """The single active producing step of *node_id*, or None.

        With the "at most one active producer" invariant the active subgraph is a
        tree, so this resolves to the one producer that carries the effective
        lineage. Falls back to the first producer when none is active (the node
        is inactive anyway) so callers always get a structural anchor.
        """
        producers = self.step_by_output_node.get(node_id)
        if not producers:
            return None
        if len(producers) == 1:
            return producers[0]
        from arctx.core.cuts import inactive_step_ids

        inactive = inactive_step_ids(self)
        for step_id in producers:
            if step_id not in inactive:
                return step_id
        return producers[0]

    def steps_to_node(self, node_id: str) -> list[str]:
        return list(self.step_by_output_node.get(node_id, ()))

    def step_inputs(self, step_id: str) -> list[str]:
        t = self.steps.get(step_id)
        return list(t.input_node_ids) if t is not None else []

    def step_output(self, step_id: str) -> str:
        t = self.steps.get(step_id)
        return t.output_node_id if t is not None else ""

    def step_outputs(self, step_id: str) -> list[str]:
        out = self.step_output(step_id)
        return [out] if out else []

    def payloads_for_node(
        self, node_id: str, *, payload_type: str | None = None
    ) -> list[PayloadBase]:
        ids = self.payloads_by_node.get(node_id, ())
        items = [self.payloads[pid] for pid in ids]
        return (
            items if payload_type is None else [p for p in items if p.payload_type == payload_type]
        )

    def payloads_for_step(
        self, step_id: str, *, payload_type: str | None = None
    ) -> list[PayloadBase]:
        ids = self.payloads_by_step.get(step_id, ())
        items = [self.payloads[pid] for pid in ids]
        return (
            items if payload_type is None else [p for p in items if p.payload_type == payload_type]
        )

    # ----- topology --------------------------------------------------------

    def reachable_from(self, node_id: str) -> dict:
        """BFS from node_id over active steps."""
        from arctx.core.cuts import is_active_node, is_inactive_step

        visited_nodes: set[str] = set()
        visited_steps: set[str] = set()

        queue: deque[tuple[str, str]] = deque()
        if node_id in self.nodes and is_active_node(self, node_id):
            queue.append(("node", node_id))

        while queue:
            kind, rid = queue.popleft()
            if kind == "node":
                if rid in visited_nodes:
                    continue
                visited_nodes.add(rid)
                for t_id in self.steps_from_node(rid):
                    if not is_inactive_step(self, t_id):
                        queue.append(("step", t_id))
            else:
                if rid in visited_steps:
                    continue
                if is_inactive_step(self, rid):
                    continue
                visited_steps.add(rid)
                out = self.step_output(rid)
                if out and is_active_node(self, out):
                    queue.append(("node", out))

        payload_ids: set[str] = set()
        for nid in visited_nodes:
            payload_ids.update(self.payloads_by_node.get(nid, ()))
        for tid in visited_steps:
            payload_ids.update(self.payloads_by_step.get(tid, ()))

        return {
            "node_ids": sorted(visited_nodes),
            "step_ids": sorted(visited_steps),
            "payload_ids": sorted(payload_ids),
        }

    def roots(self) -> list[str]:
        """Nodes with no incoming step."""
        return [nid for nid in self.nodes if nid not in self.step_by_output_node]

    # ----- ancestry --------------------------------------------------------

    def ancestors_of(self, node_id: str) -> set[str]:
        """Return all ancestor node IDs (excluding *node_id* itself).

        Walks backwards through the DAG via ``step_by_output_node``,
        collecting the input nodes of each incoming step. The walk is
        BFS and includes all ancestors regardless of cut status.

        Parameters
        ----------
        node_id:
            The node whose ancestors are requested.

        Returns
        -------
        Set of node IDs that are ancestors of *node_id* (i.e. lie on any
        path leading *to* it).
        """
        ancestors: set[str] = set()
        queue: deque[str] = deque()

        def _enqueue_parents(target: str) -> None:
            # Follow every producer (active or not): cycle detection must be
            # conservative over the full structure, not just the active edge.
            for t_id in self.step_by_output_node.get(target, ()):  # type: ignore[union-attr]
                for parent in self.steps[t_id].input_node_ids:
                    if parent not in ancestors:
                        ancestors.add(parent)
                        queue.append(parent)

        _enqueue_parents(node_id)
        while queue:
            _enqueue_parents(queue.popleft())

        return ancestors

    def to_dict(self) -> dict:
        return to_jsonable(self)  # type: ignore[return-value]
