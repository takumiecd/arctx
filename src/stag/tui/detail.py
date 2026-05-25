"""Build detail Markdown for a selected tree node."""

from __future__ import annotations

import json

from stag.core.cuts import inactive_node_ids, inactive_transition_ids
from stag.core.run.handle import RunHandle
from stag.core.schema.payloads import (
    NotePayload,
    PlanPayload,
    PredictionPayload,
    ResultPayload,
)


def build_detail_markdown(
    handle: RunHandle,
    node_data: dict | None,
    state_labels: dict[str, str],
    plan_labels: dict[str, str],
) -> str:
    """Return a Markdown string for the given tree node data dict.

    node_data keys: type, id
    Raw IDs are never exposed in the output.
    """
    if not node_data:
        return _run_overview(handle)

    kind = node_data.get("type", "")
    raw_id = node_data.get("id", "")

    if kind == "node":
        return _node_detail(handle, raw_id, state_labels, plan_labels)
    if kind == "transition":
        return _transition_detail(handle, raw_id, state_labels, plan_labels)
    if kind == "note":
        return _node_detail(handle, raw_id, state_labels, plan_labels)
    if kind == "backref":
        # Determine whether the id is a node or transition.
        if raw_id in handle.run_graph.nodes:
            sl = state_labels.get(raw_id, "?")
            return f"# Back-reference → {sl}\n\nThis state is referenced elsewhere in the tree.\n"
        else:
            pl = plan_labels.get(raw_id, "?")
            return f"# Back-reference → {pl}\n\nThis plan is referenced elsewhere in the tree.\n"
    if kind == "forward_pointer":
        pl = plan_labels.get(raw_id, "?")
        return f"# Forward Pointer → Plan {pl}\n\nThis node feeds into {pl} as a secondary input.\n"

    return _run_overview(handle)


def _run_overview(handle: RunHandle) -> str:
    graph = handle.run_graph
    req = handle.requirement
    node_count = len(graph.nodes)
    trans_count = len(graph.transitions)
    inactive_n = len(inactive_node_ids(graph))
    inactive_t = len(inactive_transition_ids(graph))

    lines = [
        f"# Run Overview",
        "",
        f"**Target:** {req.target_type} / {req.target_id}",
        "",
        f"**States:** {node_count} ({inactive_n} cut)",
        f"**Plans:** {trans_count} ({inactive_t} cut)",
    ]
    if req.objective:
        lines += ["", "**Objective:**", "```", json.dumps(req.objective, indent=2), "```"]
    return "\n".join(lines)


def _node_role(handle: RunHandle, node_id: str, state_labels: dict[str, str]) -> str:
    if node_id == handle.root_node_id:
        return "root"
    if node_id in inactive_node_ids(handle.run_graph):
        return "cut"
    incoming = handle.run_graph.transitions_to_node(node_id)
    if incoming:
        kind = handle.run_graph.transition_kind(incoming[0])
        if kind == "result":
            return "observed"
        if kind == "prediction":
            return "predicted"
    return "unknown"


def _node_detail(
    handle: RunHandle,
    node_id: str,
    state_labels: dict[str, str],
    plan_labels: dict[str, str],
) -> str:
    if node_id not in handle.run_graph.nodes:
        return "*(unknown node)*"

    graph = handle.run_graph
    sl = state_labels.get(node_id, "?")
    role = _node_role(handle, node_id, state_labels)
    incoming = graph.transitions_to_node(node_id)
    outgoing = graph.transitions_from_node(node_id)

    lines = [
        f"# State {sl}",
        "",
        f"**Role:** {role}",
        f"**Incoming plans:** {len(incoming)}",
        f"**Outgoing plans:** {len(outgoing)}",
    ]

    # Notes.
    notes = [p for p in graph.payloads_for_node(node_id) if isinstance(p, NotePayload)]
    if notes:
        lines += ["", "## Notes"]
        for note in notes:
            lines += [f"- {note.text}"]

    # If this node has an incoming transition, show the output payload (result or prediction).
    if incoming:
        tid = incoming[0]
        pl = plan_labels.get(tid, "?")
        payloads = graph.payloads_for_transition(tid)
        for payload in payloads:
            if isinstance(payload, ResultPayload):
                lines += [
                    "",
                    f"## Output ← {pl}",
                    "",
                    f"**Status:** {payload.status}",
                ]
                if payload.metrics:
                    lines += ["", "**Metrics:**", "```", json.dumps(payload.metrics, indent=2), "```"]
                if payload.errors:
                    lines += ["", "**Errors:**"]
                    for e in payload.errors:
                        lines.append(f"- {e}")
            elif isinstance(payload, PredictionPayload):
                lines += [
                    "",
                    f"## Prediction ← {pl}",
                ]
                if payload.rationale:
                    lines += [f"", f"**Rationale:** {payload.rationale}"]
                if payload.probability is not None:
                    lines += [f"**Probability:** {payload.probability:.2f}"]
                if payload.predicted_metrics:
                    lines += [
                        "",
                        "**Predicted metrics:**",
                        "```",
                        json.dumps(payload.predicted_metrics, indent=2),
                        "```",
                    ]

    return "\n".join(lines)


def _transition_detail(
    handle: RunHandle,
    transition_id: str,
    state_labels: dict[str, str],
    plan_labels: dict[str, str],
) -> str:
    if transition_id not in handle.run_graph.transitions:
        return "*(unknown transition)*"

    graph = handle.run_graph
    pl = plan_labels.get(transition_id, "?")
    inputs = graph.transition_inputs(transition_id)
    outputs = graph.transition_outputs(transition_id)
    input_labels = ", ".join(state_labels.get(n, "?") for n in inputs)

    lines = [
        f"# Plan {pl}",
        "",
        f"**From:** {input_labels}",
        f"**Outputs:** {len(outputs)}",
    ]

    # Plan payload details.
    for payload in graph.payloads_for_transition(transition_id):
        if isinstance(payload, PlanPayload):
            lines += [
                "",
                "## Plan Details",
                "",
                f"**Intent:** {payload.intent}",
                f"**Action type:** {payload.action_type}",
            ]
            if payload.inputs:
                lines += [
                    "",
                    "**Inputs:**",
                    "```",
                    json.dumps(payload.inputs, indent=2),
                    "```",
                ]
            if payload.constraints:
                lines += [
                    "",
                    "**Constraints:**",
                    "```",
                    json.dumps(payload.constraints, indent=2),
                    "```",
                ]
            if payload.assumptions:
                lines += ["", "**Assumptions:**"]
                for a in payload.assumptions:
                    lines.append(f"- {a}")

    # Result or prediction payloads.
    for payload in graph.payloads_for_transition(transition_id):
        if isinstance(payload, ResultPayload):
            lines += [
                "",
                "## Result",
                "",
                f"**Status:** {payload.status}",
            ]
            if payload.metrics:
                lines += [
                    "",
                    "**Metrics:**",
                    "```",
                    json.dumps(payload.metrics, indent=2),
                    "```",
                ]
            if payload.errors:
                lines += ["", "**Errors:**"]
                for e in payload.errors:
                    lines.append(f"- {e}")
        elif isinstance(payload, PredictionPayload):
            lines += ["", "## Prediction"]
            if payload.rationale:
                lines += [f"", f"**Rationale:** {payload.rationale}"]
            if payload.probability is not None:
                lines += [f"**Probability:** {payload.probability:.2f}"]

    return "\n".join(lines)
