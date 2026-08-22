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


def resolve_attach_target(handle, record_id: str) -> tuple[str, TargetKind, list[str]]:
    """Resolve a record id to the Node or Step a payload should land on.

    A **payload** id resolves to the record it annotates, so an id copied out
    of `arctx trials` / `arctx show` can be pasted wherever a target is asked
    for (this mirrors `arctx trial add --to`). Returns
    ``(target_id, target_kind, notes)``; *notes* are advisory lines for stderr
    — the payload hop, and a warning when the target is inactive, since a
    payload on a cut record is recorded but read as inactive.
    """
    notes: list[str] = []
    kind = resolve_target_kind(handle, record_id)
    target_id = record_id
    if kind == "payload":
        payload = handle.run_graph.payloads[record_id]
        target_id = payload.target_id
        kind = payload.target_kind
        notes.append(
            f"{record_id} is a payload; attaching to its {kind} {target_id}"
        )
    if _is_inactive(handle, target_id, kind):
        notes.append(
            f"{target_id} is cut (or downstream of a cut) — the attachment is "
            f"recorded, but every view reads it as inactive"
        )
    return target_id, kind, notes


def _is_inactive(handle, target_id: str, kind: str) -> bool:
    from arctx.core.cuts import inactive_node_ids, inactive_step_ids  # noqa: PLC0415

    graph = handle.run_graph
    if kind == "node":
        return target_id in inactive_node_ids(graph)
    return target_id in inactive_step_ids(graph)


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
