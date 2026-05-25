"""RunHandle.outcomes implementation."""

from __future__ import annotations

from stag.core.cuts import is_active_node


def outcomes_impl(self, transition_id: str) -> dict:
    """Return the output node for a transition."""
    if transition_id not in self.run_graph.transitions:
        raise KeyError(f"unknown transition_id: {transition_id}")

    output_node_id = self.run_graph.transition_output(transition_id)
    output_node_ids = [output_node_id] if output_node_id else []
    active_output_node_ids = [
        node_id for node_id in output_node_ids if is_active_node(self.run_graph, node_id)
    ]
    active_set = set(active_output_node_ids)
    inactive_output_node_ids = [node_id for node_id in output_node_ids if node_id not in active_set]

    return {
        "transition_id": transition_id,
        "output_node_ids": output_node_ids,
        "active_output_node_ids": active_output_node_ids,
        "inactive_output_node_ids": inactive_output_node_ids,
    }
