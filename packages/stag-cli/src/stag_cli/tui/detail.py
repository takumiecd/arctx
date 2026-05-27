"""Build detail Markdown for a selected tree node."""

from __future__ import annotations

import json

from stag_api.core.cuts import inactive_node_ids, inactive_transition_ids
from stag_api.core.run.handle import RunHandle
from stag_api.core.schema.payloads import (
    CutPayload,
    NodePayload,
    TransitionPayload,
)
from stag_api.ext.git.payloads import GitChangePayload


def build_detail_markdown(
    handle: RunHandle,
    node_data: dict | None,
    state_labels: dict[str, str],
    plan_labels: dict[str, str],
) -> str:
    """Return a Markdown string for the given tree node data dict.

    node_data keys: type, id
    """
    if not node_data:
        return _run_overview(handle)

    kind = node_data.get("type", "")
    raw_id = node_data.get("id", "")

    if kind in ("node", "note"):
        return _node_detail(handle, raw_id, state_labels, plan_labels)
    if kind == "transition":
        return _transition_detail(handle, raw_id, state_labels, plan_labels)

    return _run_overview(handle)


def _run_overview(handle: RunHandle) -> str:
    graph = handle.run_graph
    req = handle.requirement
    node_count = len(graph.nodes)
    trans_count = len(graph.transitions)
    inactive_n = len(inactive_node_ids(graph))
    inactive_t = len(inactive_transition_ids(graph))

    lines = [
        "# Run Overview",
        "",
        f"**Target:** {req.target_type} / {req.target_id}",
        "",
        f"**Nodes:** {node_count} ({inactive_n} cut)",
        f"**Transitions:** {trans_count} ({inactive_t} cut)",
    ]
    if req.objective:
        lines += ["", "**Objective:**", "```", json.dumps(req.objective, indent=2), "```"]
    return "\n".join(lines)


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
    is_root = node_id == handle.root_node_id
    is_cut = node_id in inactive_node_ids(graph)
    role = "root" if is_root else "cut" if is_cut else "active"

    incoming = graph.transitions_to_node(node_id)
    outgoing = graph.transitions_from_node(node_id)

    lines = [
        f"# Node {sl}",
        "",
        f"**Role:** {role}",
        f"**Incoming:** {len(incoming)}",
        f"**Outgoing:** {len(outgoing)}",
    ]

    # Node payloads.
    for payload in graph.payloads_for_node(node_id):
        if isinstance(payload, CutPayload):
            lines += ["", "## Cut"]
            if payload.reason:
                lines.append(f"**Reason:** {payload.reason}")
        elif isinstance(payload, NodePayload):
            lines += ["", f"## {payload.type}"]
            if payload.content:
                lines += ["```", json.dumps(payload.content, indent=2, ensure_ascii=False), "```"]
        else:
            lines += ["", f"## Payload ({payload.payload_type})"]
            lines += ["```", json.dumps(payload.to_dict(), indent=2, ensure_ascii=False), "```"]

    # Incoming transition detail (transition is no longer a selectable tree row).
    if not is_root and incoming:
        transition_id = incoming[0]
        pl = plan_labels.get(transition_id, "?")
        inputs = graph.transition_inputs(transition_id)
        input_labels = ", ".join(state_labels.get(n, "?") for n in inputs)

        lines += ["", "## Incoming", "", f"**Transition:** {pl}", f"**From:** {input_labels}"]

        for payload in graph.payloads_for_transition(transition_id):
            if isinstance(payload, CutPayload):
                lines += ["", "### Cut"]
                if payload.reason:
                    lines.append(f"**Reason:** {payload.reason}")
            elif isinstance(payload, GitChangePayload):
                diff = payload.diff_summary
                lines += [
                    "",
                    "### Git Change",
                    "",
                    f"**Branch:** {payload.branch}",
                    f"**Head:** `{payload.head_commit[:12]}`",
                    f"**Diff:** +{diff.insertions} / -{diff.deletions} in {diff.files_changed} files",
                ]
                if payload.commit_log:
                    lines += ["", "**Commits:**"]
                    for c in payload.commit_log[:5]:
                        lines.append(f"- `{c.sha[:8]}` {c.subject}")
            elif isinstance(payload, TransitionPayload):
                lines += ["", f"### {payload.type}"]
                if payload.content:
                    lines += ["```", json.dumps(payload.content, indent=2, ensure_ascii=False), "```"]
            else:
                lines += ["", f"### Payload ({payload.payload_type})"]
                lines += ["```", json.dumps(payload.to_dict(), indent=2, ensure_ascii=False), "```"]

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
    output = graph.transition_output(transition_id)
    input_labels = ", ".join(state_labels.get(n, "?") for n in inputs)
    output_label = state_labels.get(output, "?") if output else "-"

    lines = [
        f"# Transition {pl}",
        "",
        f"**From:** {input_labels}",
        f"**To:** {output_label}",
    ]

    for payload in graph.payloads_for_transition(transition_id):
        if isinstance(payload, CutPayload):
            lines += ["", "## Cut"]
            if payload.reason:
                lines.append(f"**Reason:** {payload.reason}")
        elif isinstance(payload, GitChangePayload):
            diff = payload.diff_summary
            lines += [
                "",
                "## Git Change",
                "",
                f"**Branch:** {payload.branch}",
                f"**Head:** `{payload.head_commit[:12]}`",
                f"**Diff:** +{diff.insertions} / -{diff.deletions} in {diff.files_changed} files",
            ]
            if payload.commit_log:
                lines += ["", "**Commits:**"]
                for c in payload.commit_log[:5]:
                    lines.append(f"- `{c.sha[:8]}` {c.subject}")
        elif isinstance(payload, TransitionPayload):
            lines += ["", f"## {payload.type}"]
            if payload.content:
                lines += ["```", json.dumps(payload.content, indent=2, ensure_ascii=False), "```"]
        else:
            lines += ["", f"## Payload ({payload.payload_type})"]
            lines += ["```", json.dumps(payload.to_dict(), indent=2, ensure_ascii=False), "```"]

    return "\n".join(lines)
