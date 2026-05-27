"""Single global DAG container for a run."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from stag_api.core.graph_view import GraphView
from stag_api.core.schema.graph import Node, Transition
from stag_api.core.schema.payloads import PayloadBase
from stag_api.core.schema.work import WorkEvent, WorkSession
from stag_api.core.types import JSONValue, to_jsonable


@dataclass
class RunGraph:
    """Append-only graph records for one run."""

    nodes: dict[str, Node] = field(default_factory=dict)
    transitions: dict[str, Transition] = field(default_factory=dict)
    payloads: dict[str, PayloadBase] = field(default_factory=dict)
    views: dict[str, GraphView] = field(default_factory=dict)
    work_sessions: dict[str, WorkSession] = field(default_factory=dict)
    work_events: list[WorkEvent] = field(default_factory=list)

    # Reverse-lookup indices (not persisted; rebuilt on load).
    transitions_by_input_node: dict[str, list[str]] = field(default_factory=dict)
    transition_by_output_node: dict[str, str] = field(default_factory=dict)
    payloads_by_node: dict[str, list[str]] = field(default_factory=dict)
    payloads_by_transition: dict[str, list[str]] = field(default_factory=dict)

    metadata: dict[str, JSONValue] = field(default_factory=dict)

    # ----- views -----------------------------------------------------------

    def add_view(self, view: GraphView) -> None:
        if view.name in self.views:
            raise ValueError(f"duplicate view name: {view.name!r}")
        if view.root_node_id not in self.nodes:
            raise KeyError(f"unknown root_node_id: {view.root_node_id}")
        self.views[view.name] = view

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

    def add_transition(self, transition: Transition) -> None:
        if transition.transition_id in self.transitions:
            raise ValueError(f"duplicate transition_id: {transition.transition_id}")
        # Validate output node exists.
        if transition.output_node_id and transition.output_node_id not in self.nodes:
            raise KeyError(f"unknown output_node_id: {transition.output_node_id}")
        # Validate each input node exists.
        for nid in transition.input_node_ids:
            if nid not in self.nodes:
                raise KeyError(f"unknown input_node_id: {nid}")
        # Enforce uniqueness: output node must belong to exactly one transition.
        if transition.output_node_id:
            if transition.output_node_id in self.transition_by_output_node:
                existing = self.transition_by_output_node[transition.output_node_id]
                raise ValueError(
                    f"output_node_id {transition.output_node_id!r} already used by "
                    f"transition {existing!r}"
                )
            self.transition_by_output_node[transition.output_node_id] = transition.transition_id
        for nid in transition.input_node_ids:
            self.transitions_by_input_node.setdefault(nid, []).append(transition.transition_id)
        self.transitions[transition.transition_id] = transition

    def attach_payload(self, payload: PayloadBase) -> None:
        if payload.payload_id in self.payloads:
            raise ValueError(f"duplicate payload_id: {payload.payload_id}")
        if payload.target_kind == "node":
            if payload.target_id not in self.nodes:
                raise KeyError(f"unknown target node: {payload.target_id}")
            self.payloads_by_node.setdefault(payload.target_id, []).append(payload.payload_id)
        elif payload.target_kind == "transition":
            if payload.target_id not in self.transitions:
                raise KeyError(f"unknown target transition: {payload.target_id}")
            self.payloads_by_transition.setdefault(payload.target_id, []).append(payload.payload_id)
        else:
            raise ValueError(f"unknown target_kind: {payload.target_kind!r}")
        self.payloads[payload.payload_id] = payload

    # ----- lookup ----------------------------------------------------------

    def transitions_from_node(self, node_id: str) -> list[str]:
        return list(self.transitions_by_input_node.get(node_id, ()))

    def transition_to_node(self, node_id: str) -> str | None:
        return self.transition_by_output_node.get(node_id)

    def transitions_to_node(self, node_id: str) -> list[str]:
        t_id = self.transition_by_output_node.get(node_id)
        return [t_id] if t_id is not None else []

    def transition_inputs(self, transition_id: str) -> list[str]:
        t = self.transitions.get(transition_id)
        return list(t.input_node_ids) if t is not None else []

    def transition_output(self, transition_id: str) -> str:
        t = self.transitions.get(transition_id)
        return t.output_node_id if t is not None else ""

    def transition_outputs(self, transition_id: str) -> list[str]:
        out = self.transition_output(transition_id)
        return [out] if out else []

    def payloads_for_node(
        self, node_id: str, *, payload_type: str | None = None
    ) -> list[PayloadBase]:
        ids = self.payloads_by_node.get(node_id, ())
        items = [self.payloads[pid] for pid in ids]
        return (
            items if payload_type is None else [p for p in items if p.payload_type == payload_type]
        )

    def payloads_for_transition(
        self, transition_id: str, *, payload_type: str | None = None
    ) -> list[PayloadBase]:
        ids = self.payloads_by_transition.get(transition_id, ())
        items = [self.payloads[pid] for pid in ids]
        return (
            items if payload_type is None else [p for p in items if p.payload_type == payload_type]
        )

    # ----- topology --------------------------------------------------------

    def reachable_from(self, node_id: str) -> dict:
        """BFS from node_id over active transitions."""
        from stag_api.core.cuts import is_active_node, is_inactive_transition

        visited_nodes: set[str] = set()
        visited_transitions: set[str] = set()

        queue: deque[tuple[str, str]] = deque()
        if node_id in self.nodes and is_active_node(self, node_id):
            queue.append(("node", node_id))

        while queue:
            kind, rid = queue.popleft()
            if kind == "node":
                if rid in visited_nodes:
                    continue
                visited_nodes.add(rid)
                for t_id in self.transitions_from_node(rid):
                    if not is_inactive_transition(self, t_id):
                        queue.append(("transition", t_id))
            else:
                if rid in visited_transitions:
                    continue
                if is_inactive_transition(self, rid):
                    continue
                visited_transitions.add(rid)
                out = self.transition_output(rid)
                if out and is_active_node(self, out):
                    queue.append(("node", out))

        payload_ids: set[str] = set()
        for nid in visited_nodes:
            payload_ids.update(self.payloads_by_node.get(nid, ()))
        for tid in visited_transitions:
            payload_ids.update(self.payloads_by_transition.get(tid, ()))

        return {
            "node_ids": sorted(visited_nodes),
            "transition_ids": sorted(visited_transitions),
            "payload_ids": sorted(payload_ids),
        }

    def roots(self) -> list[str]:
        """Nodes with no incoming transition."""
        return [nid for nid in self.nodes if nid not in self.transition_by_output_node]

    # ----- ancestry --------------------------------------------------------

    def ancestors_of(self, node_id: str) -> set[str]:
        """Return all ancestor node IDs (excluding *node_id* itself).

        Walks backwards through the DAG via ``transition_by_output_node``,
        collecting the input nodes of each incoming transition. The walk is
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
        t_id = self.transition_by_output_node.get(node_id)
        if t_id is not None:
            transition = self.transitions[t_id]
            for parent in transition.input_node_ids:
                if parent not in ancestors:
                    ancestors.add(parent)
                    queue.append(parent)

        while queue:
            current = queue.popleft()
            t_id = self.transition_by_output_node.get(current)
            if t_id is None:
                continue
            transition = self.transitions[t_id]
            for parent in transition.input_node_ids:
                if parent not in ancestors:
                    ancestors.add(parent)
                    queue.append(parent)

        return ancestors

    def to_dict(self) -> dict:
        return to_jsonable(self)  # type: ignore[return-value]
