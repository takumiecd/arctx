"""Helpers for resolving user-facing DAG record IDs."""

from __future__ import annotations

from typing import Literal


TargetKind = Literal["node", "step", "payload"]


def resolve_target_kind(handle, record_id: str) -> TargetKind:
    """Resolve a record id to its internal target kind."""
    graph = handle.run_graph
    matches: list[TargetKind] = []
    if record_id in graph.nodes:
        matches.append("node")
    if record_id in graph.steps:
        matches.append("step")
    if record_id in graph.payloads:
        matches.append("payload")
    if not matches:
        raise KeyError(f"unknown record_id: {record_id}")
    if len(matches) > 1:
        raise ValueError(f"ambiguous record_id {record_id!r}: {matches}")
    return matches[0]


def step_view(step) -> dict:
    """Return a user-facing Step view for an internal Step."""
    return {
        "kind": "step",
        "id": step.step_id,
        "step_id": step.step_id,
        "step_id": step.step_id,
        "input_node_ids": list(step.input_node_ids),
        "output_node_id": step.output_node_id,
        "metadata": dict(step.metadata),
    }
