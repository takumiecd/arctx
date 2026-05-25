"""Read-time computation of inactive transitions and nodes."""

from __future__ import annotations

from stag.core.run_graph import RunGraph
from stag.core.schema.payloads import CutPayload


def _cut_payloads(graph: RunGraph) -> list[CutPayload]:
    return [p for p in graph.payloads.values() if isinstance(p, CutPayload)]


def cut_transition_ids(graph: RunGraph) -> set[str]:
    return {p.target_id for p in _cut_payloads(graph) if p.target_kind == "transition"}


def cut_node_ids(graph: RunGraph) -> set[str]:
    return {p.target_id for p in _cut_payloads(graph) if p.target_kind == "node"}


def _compute_inactive(graph: RunGraph) -> tuple[set[str], set[str]]:
    inactive_transitions: set[str] = set(cut_transition_ids(graph))
    inactive_nodes: set[str] = set(cut_node_ids(graph))

    frontier_nodes = list(inactive_nodes)
    frontier_transitions = list(inactive_transitions)

    while frontier_nodes or frontier_transitions:
        while frontier_transitions:
            transition_id = frontier_transitions.pop()
            out = graph.transition_output(transition_id)
            if out and out not in inactive_nodes:
                inactive_nodes.add(out)
                frontier_nodes.append(out)

        while frontier_nodes:
            node_id = frontier_nodes.pop()
            for transition_id in graph.transitions_from_node(node_id):
                if transition_id not in inactive_transitions:
                    inactive_transitions.add(transition_id)
                    frontier_transitions.append(transition_id)

    return inactive_transitions, inactive_nodes


def inactive_transition_ids(graph: RunGraph) -> set[str]:
    inactive_transitions, _ = _compute_inactive(graph)
    return inactive_transitions


def inactive_node_ids(graph: RunGraph) -> set[str]:
    _, inactive_nodes = _compute_inactive(graph)
    return inactive_nodes


def is_active_node(graph: RunGraph, node_id: str) -> bool:
    return node_id not in inactive_node_ids(graph)


def is_inactive_transition(graph: RunGraph, transition_id: str) -> bool:
    return transition_id in inactive_transition_ids(graph)
