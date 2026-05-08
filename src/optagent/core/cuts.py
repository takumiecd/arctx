"""Read-time computation of inactive transitions and nodes.

CutPayloads are attached to InputTransitions or OutputTransitions.
Activity is derived here at read time — no state is stored on records.

- CutPayload on InputTransition: that IT + all its OTs become inactive,
  and the downstream nodes become inactive (cascading forward).
- CutPayload on OutputTransition: only that OT becomes inactive,
  and its to_node (and descendants) become inactive.
"""

from __future__ import annotations

from optagent.core.run_graph import RunGraph
from optagent.core.schema.payloads import CutPayload


def _cut_payloads(graph: RunGraph) -> list[CutPayload]:
    return [p for p in graph.payloads.values() if isinstance(p, CutPayload)]


def cut_input_transition_ids(graph: RunGraph) -> set[str]:
    """IDs of InputTransitions directly marked with a CutPayload."""
    return {p.target_id for p in _cut_payloads(graph) if p.target_kind == "input_transition"}


def cut_output_transition_ids(graph: RunGraph) -> set[str]:
    """IDs of OutputTransitions directly marked with a CutPayload."""
    return {p.target_id for p in _cut_payloads(graph) if p.target_kind == "output_transition"}


def _compute_inactive(graph: RunGraph) -> tuple[set[str], set[str]]:
    """Return (inactive_ot_ids, inactive_node_ids) via a single forward BFS."""
    # Seed: OTs directly cut + OTs from cut ITs
    inactive_ots: set[str] = set(cut_output_transition_ids(graph))
    for it_id in cut_input_transition_ids(graph):
        inactive_ots.update(graph.output_transitions_from_it.get(it_id, ()))

    # BFS forward from inactive OT destinations
    inactive_nodes: set[str] = set()
    frontier: list[str] = []
    for ot_id in inactive_ots:
        ot = graph.output_transitions.get(ot_id)
        if ot is not None:
            frontier.append(ot.to_node_id)

    while frontier:
        nid = frontier.pop()
        if nid in inactive_nodes:
            continue
        inactive_nodes.add(nid)
        for it_id in graph.input_transitions_from_node.get(nid, ()):
            for ot_id in graph.output_transitions_from_it.get(it_id, ()):
                inactive_ots.add(ot_id)
                ot = graph.output_transitions.get(ot_id)
                if ot is not None:
                    frontier.append(ot.to_node_id)

    return inactive_ots, inactive_nodes


def inactive_output_transition_ids(graph: RunGraph) -> set[str]:
    """All OT IDs that are inactive (directly or by cascade)."""
    inactive_ots, _ = _compute_inactive(graph)
    return inactive_ots


def inactive_node_ids(graph: RunGraph) -> set[str]:
    """All node IDs reachable forward from any inactive OT."""
    _, inactive_nodes = _compute_inactive(graph)
    return inactive_nodes


def is_active_node(graph: RunGraph, node_id: str) -> bool:
    return node_id not in inactive_node_ids(graph)


def is_inactive_output_transition(graph: RunGraph, ot_id: str) -> bool:
    return ot_id in inactive_output_transition_ids(graph)
