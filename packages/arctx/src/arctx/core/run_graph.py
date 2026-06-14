"""Single global DAG container for a run."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from arctx.core.schema.graph import Node, Step
from arctx.core.schema.payloads import PayloadBase
from arctx.core.schema.work import WorkEvent, WorkSession
from arctx.core.types import JSONValue, to_jsonable


@dataclass
class RunGraph:
    """Append-only graph records for one run."""

    nodes: dict[str, Node] = field(default_factory=dict)
    steps: dict[str, Step] = field(default_factory=dict)
    payloads: dict[str, PayloadBase] = field(default_factory=dict)
    work_sessions: dict[str, WorkSession] = field(default_factory=dict)
    work_events: list[WorkEvent] = field(default_factory=list)

    # Reverse-lookup indices (not persisted; rebuilt on load).
    steps_by_input_node: dict[str, list[str]] = field(default_factory=dict)
    step_by_output_node: dict[str, str] = field(default_factory=dict)
    payloads_by_node: dict[str, list[str]] = field(default_factory=dict)
    payloads_by_step: dict[str, list[str]] = field(default_factory=dict)

    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def add_work_session(self, session: WorkSession) -> None:
        if session.work_session_id in self.work_sessions:
            existing = self.work_sessions[session.work_session_id]
            if existing.user_id != session.user_id:
                raise ValueError(
                    f"work_session_id {session.work_session_id!r} belongs to "
                    f"user {existing.user_id!r}, not {session.user_id!r}"
                )
            return
        self.work_sessions[session.work_session_id] = session

    def add_work_event(self, event: WorkEvent) -> None:
        if event.work_session_id not in self.work_sessions:
            raise KeyError(f"unknown work_session_id: {event.work_session_id}")
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
        # Enforce uniqueness: output node must belong to exactly one step.
        if step.output_node_id:
            if step.output_node_id in self.step_by_output_node:
                existing = self.step_by_output_node[step.output_node_id]
                raise ValueError(
                    f"output_node_id {step.output_node_id!r} already used by "
                    f"step {existing!r}"
                )
            self.step_by_output_node[step.output_node_id] = step.step_id
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

    def step_to_node(self, node_id: str) -> str | None:
        return self.step_by_output_node.get(node_id)

    def steps_to_node(self, node_id: str) -> list[str]:
        t_id = self.step_by_output_node.get(node_id)
        return [t_id] if t_id is not None else []

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

        # Seed with the direct parents of node_id.
        t_id = self.step_by_output_node.get(node_id)
        if t_id is not None:
            step = self.steps[t_id]
            for parent in step.input_node_ids:
                if parent not in ancestors:
                    ancestors.add(parent)
                    queue.append(parent)

        while queue:
            current = queue.popleft()
            t_id = self.step_by_output_node.get(current)
            if t_id is None:
                continue
            step = self.steps[t_id]
            for parent in step.input_node_ids:
                if parent not in ancestors:
                    ancestors.add(parent)
                    queue.append(parent)

        return ancestors

    def to_dict(self) -> dict:
        return to_jsonable(self)  # type: ignore[return-value]
