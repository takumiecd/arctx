"""Helpers for resolving user-facing DAG record IDs."""

from __future__ import annotations

from typing import Literal


TargetKind = Literal["node", "transition", "payload"]


def resolve_target_kind(handle, record_id: str) -> TargetKind:
    """Resolve a record id to its internal target kind."""
    graph = handle.run_graph
    matches: list[TargetKind] = []
    if record_id in graph.nodes:
        matches.append("node")
    if record_id in graph.transitions:
        matches.append("transition")
    if record_id in graph.payloads:
        matches.append("payload")
    if not matches:
        raise KeyError(f"unknown record_id: {record_id}")
    if len(matches) > 1:
        raise ValueError(f"ambiguous record_id {record_id!r}: {matches}")
    return matches[0]


def step_view(transition) -> dict:
    """Return a user-facing Step view for an internal Transition."""
    return {
        "kind": "step",
        "id": transition.transition_id,
        "step_id": transition.transition_id,
        "transition_id": transition.transition_id,
        "input_node_ids": list(transition.input_node_ids),
        "output_node_id": transition.output_node_id,
        "metadata": dict(transition.metadata),
    }
