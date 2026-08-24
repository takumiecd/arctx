"""Read-time computation of inactive steps and nodes."""

from __future__ import annotations

from arctx.core.run_graph import RunGraph
from arctx.core.schema.payloads import CutPayload, UncutPayload


def _effective_cut_state(graph: RunGraph) -> tuple[dict[str, bool], dict[str, bool]]:
    """Resolve cut/uncut markers to current cut state per target.

    Cut and uncut markers are append-only; the **last** marker on a target wins
    (supersession). Payloads are iterated in insertion order, which mirrors the
    order they were recorded, so a later uncut reverses an earlier cut and a
    later cut reverses an earlier uncut.
    """
    node_state: dict[str, bool] = {}
    step_state: dict[str, bool] = {}
    for payload in graph.payloads.values():
        if isinstance(payload, CutPayload):
            cut = True
        elif isinstance(payload, UncutPayload):
            cut = False
        else:
            continue
        target = node_state if payload.target_kind == "node" else step_state
        target[payload.target_id] = cut
    return node_state, step_state


def cut_step_ids(graph: RunGraph) -> set[str]:
    _, step_state = _effective_cut_state(graph)
    return {tid for tid, cut in step_state.items() if cut}


def cut_node_ids(graph: RunGraph) -> set[str]:
    node_state, _ = _effective_cut_state(graph)
    return {nid for nid, cut in node_state.items() if cut}


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


def nodes_with_multiple_active_producers(
    graph: RunGraph,
) -> list[tuple[str, list[str]]]:
    """Return ``(node_id, active_producer_step_ids)`` for every broken node.

    A node may have many producing Steps but at most one active — that is what
    keeps the active subgraph a tree, and what makes append-only re-parenting
    mean anything. Nothing checked it at read time, so a node that ended up with
    two active producers was reported by `trace` and `export` as a merged
    lineage that never happened, while `arctx lane validate` and `arctx doctor`
    both said healthy.

    Two routes get a run into that state: concurrent writers (validation happens
    outside the run lock, so two `reparent` calls can both pass the guard) and a
    git merge of two branches that each re-parented the same node. This is a
    detector, not a preventer — it covers both routes and makes the state loud.
    """
    inactive = inactive_step_ids(graph)
    broken: list[tuple[str, list[str]]] = []
    for node_id in graph.nodes:
        active = [
            step_id
            for step_id in graph.producers_of(node_id)
            if step_id not in inactive
        ]
        if len(active) > 1:
            broken.append((node_id, sorted(active)))
    return broken
