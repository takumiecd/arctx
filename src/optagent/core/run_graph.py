"""Single global graph container for a run.

RunGraph holds all nodes, input/output transitions, and payloads in one
place with no role-based sub-graphs. GraphView provides filtered subsets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.schema.graph import InputTransition, Node, OutputTransition
from optagent.core.schema.payloads import Payload
from optagent.core.types import JSONValue, to_jsonable


@dataclass
class RunGraph:
    """All records for one run, stored in flat dicts with supporting indices."""

    nodes: dict[str, Node] = field(default_factory=dict)
    input_transitions: dict[str, InputTransition] = field(default_factory=dict)
    output_transitions: dict[str, OutputTransition] = field(default_factory=dict)
    payloads: dict[str, Payload] = field(default_factory=dict)

    # payload lookup by target
    payloads_by_node: dict[str, list[str]] = field(default_factory=dict)
    payloads_by_input_transition: dict[str, list[str]] = field(default_factory=dict)
    payloads_by_output_transition: dict[str, list[str]] = field(default_factory=dict)

    # graph traversal indices
    # node_id → list[input_transition_id] where node appears in input_node_ids
    input_transitions_from_node: dict[str, list[str]] = field(default_factory=dict)
    # it_id → list[output_transition_id]
    output_transitions_from_it: dict[str, list[str]] = field(default_factory=dict)
    # to_node_id → list[output_transition_id]
    output_transitions_to_node: dict[str, list[str]] = field(default_factory=dict)

    metadata: dict[str, JSONValue] = field(default_factory=dict)

    # ----- mutations -------------------------------------------------------

    def add_node(self, node: Node) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_input_transition(self, it: InputTransition) -> None:
        if it.input_transition_id in self.input_transitions:
            raise ValueError(f"duplicate input_transition_id: {it.input_transition_id}")
        for nid in it.input_node_ids:
            if nid not in self.nodes:
                raise KeyError(f"unknown input node_id: {nid}")
        self.input_transitions[it.input_transition_id] = it
        for nid in it.input_node_ids:
            self.input_transitions_from_node.setdefault(nid, []).append(it.input_transition_id)

    def add_output_transition(self, ot: OutputTransition) -> None:
        if ot.output_transition_id in self.output_transitions:
            raise ValueError(f"duplicate output_transition_id: {ot.output_transition_id}")
        if ot.input_transition_id not in self.input_transitions:
            raise KeyError(f"unknown input_transition_id: {ot.input_transition_id}")
        if ot.to_node_id not in self.nodes:
            raise KeyError(f"unknown to_node_id: {ot.to_node_id}")
        self.output_transitions[ot.output_transition_id] = ot
        self.output_transitions_from_it.setdefault(ot.input_transition_id, []).append(
            ot.output_transition_id
        )
        self.output_transitions_to_node.setdefault(ot.to_node_id, []).append(
            ot.output_transition_id
        )

    # ----- payloads --------------------------------------------------------

    def attach_payload(self, payload: Payload) -> None:
        if payload.payload_id in self.payloads:
            raise ValueError(f"duplicate payload_id: {payload.payload_id}")
        if payload.target_kind == "node":
            if payload.target_id not in self.nodes:
                raise KeyError(f"unknown target node: {payload.target_id}")
            self.payloads_by_node.setdefault(payload.target_id, []).append(payload.payload_id)
        elif payload.target_kind == "input_transition":
            if payload.target_id not in self.input_transitions:
                raise KeyError(f"unknown target input_transition: {payload.target_id}")
            self.payloads_by_input_transition.setdefault(payload.target_id, []).append(
                payload.payload_id
            )
        elif payload.target_kind == "output_transition":
            if payload.target_id not in self.output_transitions:
                raise KeyError(f"unknown target output_transition: {payload.target_id}")
            self.payloads_by_output_transition.setdefault(payload.target_id, []).append(
                payload.payload_id
            )
        else:
            raise ValueError(f"unknown target_kind: {payload.target_kind!r}")
        self.payloads[payload.payload_id] = payload

    def payloads_for_node(
        self, node_id: str, *, payload_type: str | None = None
    ) -> list[Payload]:
        ids = self.payloads_by_node.get(node_id, ())
        items = [self.payloads[pid] for pid in ids]
        return items if payload_type is None else [p for p in items if p.payload_type == payload_type]

    def payloads_for_input_transition(
        self, it_id: str, *, payload_type: str | None = None
    ) -> list[Payload]:
        ids = self.payloads_by_input_transition.get(it_id, ())
        items = [self.payloads[pid] for pid in ids]
        return items if payload_type is None else [p for p in items if p.payload_type == payload_type]

    def payloads_for_output_transition(
        self, ot_id: str, *, payload_type: str | None = None
    ) -> list[Payload]:
        ids = self.payloads_by_output_transition.get(ot_id, ())
        items = [self.payloads[pid] for pid in ids]
        return items if payload_type is None else [p for p in items if p.payload_type == payload_type]

    # ----- topology --------------------------------------------------------

    def roots(self) -> list[str]:
        """Nodes with no incoming OutputTransition."""
        has_incoming = {ot.to_node_id for ot in self.output_transitions.values()}
        return [nid for nid in self.nodes if nid not in has_incoming]

    def to_dict(self) -> dict:
        return to_jsonable(self)  # type: ignore[return-value]
