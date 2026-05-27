"""RunHandle.trace implementation."""

from __future__ import annotations

from collections import deque

from arctx.core.cuts import is_inactive_transition
from arctx.core.schema.snapshots import TraceContext


def trace_impl(
    self,
    node_id: str,
    *,
    depth: int | None = None,
    include_raw_refs: bool = True,
) -> TraceContext:
    """Walk history backwards from a node via transition edges."""
    if node_id not in self.run_graph.nodes:
        raise KeyError(f"unknown node_id: {node_id}")

    past_node_ids: set[str] = set()
    transition_ids: list[str] = []
    payload_ids: list[str] = []

    queue: deque[tuple[str, int | None]] = deque()
    queue.append((node_id, depth))
    visited_nodes: set[str] = {node_id}

    while queue:
        current, remaining = queue.popleft()
        if remaining is not None and remaining <= 0:
            continue

        incoming = self.run_graph.transitions_to_node(current)
        for transition_id in incoming:
            if is_inactive_transition(self.run_graph, transition_id):
                continue
            transition_ids.append(transition_id)
            for p in self.run_graph.payloads_for_transition(transition_id):
                payload_ids.append(p.payload_id)

            next_remaining = None if remaining is None else remaining - 1
            for parent_id in self.run_graph.transition_inputs(transition_id):
                if parent_id in visited_nodes:
                    continue
                visited_nodes.add(parent_id)
                past_node_ids.add(parent_id)
                for p in self.run_graph.payloads_for_node(parent_id):
                    payload_ids.append(p.payload_id)
                queue.append((parent_id, next_remaining))

    # Include payloads on the current node itself.
    for p in self.run_graph.payloads_for_node(node_id):
        if p.payload_id not in payload_ids:
            payload_ids.append(p.payload_id)

    return TraceContext(
        current_node_id=node_id,
        past_node_ids=tuple(sorted(past_node_ids)),
        transition_ids=tuple(sorted(set(transition_ids))),
        payload_ids=tuple(sorted(set(payload_ids))),
    )
