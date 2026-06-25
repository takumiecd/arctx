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
    """Propagate cuts to a fixpoint.

    Two monotone rules, iterated until stable:

    - A Step is inactive if it is cut, or if **any** of its input nodes is
      inactive (a step cannot run on a dead input).
    - A Node is inactive if it is cut, or if it has producing steps and
      **all** of them are inactive. A node with at least one active producer
      stays active — this is what makes append-only re-parent work.

    With the "one active producer per node" invariant this reduces to the old
    behavior for any node that has a single producer.
    """
    inactive_steps: set[str] = set(cut_step_ids(graph))
    inactive_nodes: set[str] = set(cut_node_ids(graph))

    # Producers per node (all producing steps, active or not).
    producers: dict[str, list[str]] = {}
    for step_id, step in graph.steps.items():
        if step.output_node_id:
            producers.setdefault(step.output_node_id, []).append(step_id)

    changed = True
    while changed:
        changed = False

        for step_id, step in graph.steps.items():
            if step_id in inactive_steps:
                continue
            if any(nid in inactive_nodes for nid in step.input_node_ids):
                inactive_steps.add(step_id)
                changed = True

        for node_id, prod in producers.items():
            if node_id in inactive_nodes:
                continue
            if all(step_id in inactive_steps for step_id in prod):
                inactive_nodes.add(node_id)
                changed = True

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
