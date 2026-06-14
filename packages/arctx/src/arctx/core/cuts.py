"""Read-time computation of inactive steps and nodes."""

from __future__ import annotations

from arctx.core.run_graph import RunGraph
from arctx.core.schema.payloads import CutPayload


def _cut_payloads(graph: RunGraph) -> list[CutPayload]:
    return [p for p in graph.payloads.values() if isinstance(p, CutPayload)]


def cut_step_ids(graph: RunGraph) -> set[str]:
    return {p.target_id for p in _cut_payloads(graph) if p.target_kind == "step"}


def cut_node_ids(graph: RunGraph) -> set[str]:
    return {p.target_id for p in _cut_payloads(graph) if p.target_kind == "node"}


def _compute_inactive(graph: RunGraph) -> tuple[set[str], set[str]]:
    inactive_steps: set[str] = set(cut_step_ids(graph))
    inactive_nodes: set[str] = set(cut_node_ids(graph))

    frontier_nodes = list(inactive_nodes)
    frontier_steps = list(inactive_steps)

    while frontier_nodes or frontier_steps:
        while frontier_steps:
            step_id = frontier_steps.pop()
            out = graph.step_output(step_id)
            if out and out not in inactive_nodes:
                inactive_nodes.add(out)
                frontier_nodes.append(out)

        while frontier_nodes:
            node_id = frontier_nodes.pop()
            for step_id in graph.steps_from_node(node_id):
                if step_id not in inactive_steps:
                    inactive_steps.add(step_id)
                    frontier_steps.append(step_id)

    return inactive_steps, inactive_nodes


def inactive_step_ids(graph: RunGraph) -> set[str]:
    inactive_steps, _ = _compute_inactive(graph)
    return inactive_steps


def inactive_node_ids(graph: RunGraph) -> set[str]:
    _, inactive_nodes = _compute_inactive(graph)
    return inactive_nodes


def is_active_node(graph: RunGraph, node_id: str) -> bool:
    return node_id not in inactive_node_ids(graph)


def is_inactive_step(graph: RunGraph, step_id: str) -> bool:
    return step_id in inactive_step_ids(graph)
