"""Dump RunGraph as outline or mermaid."""

from __future__ import annotations

from dataclasses import dataclass

from stag.core.cuts import inactive_node_ids, inactive_transition_ids
from stag.core.run.handle import RunHandle
from stag.core.run_graph import RunGraph
from stag.core.schema.payloads import CutPayload, GitChangePayload, NodePayload, TransitionPayload


@dataclass
class DumpOptions:
    node_id: str | None = None
    depth: int | None = None
    full_payloads: bool = False
    observed_only: bool = False   # unused after schema change; kept for CLI compat
    predicted_only: bool = False  # unused after schema change; kept for CLI compat


def _truncate(s: str | None, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[: n - 1] + "…"


def _node_summary(graph: RunGraph, node_id: str) -> str | None:
    for payload in graph.payloads_for_node(node_id):
        if isinstance(payload, NodePayload):
            text = payload.content.get("text")
            if isinstance(text, str) and text:
                return text
            return payload.type
    return None


def _transition_summary(graph: RunGraph, transition_id: str, full: bool) -> str:
    payloads = graph.payloads_for_transition(transition_id)
    parts = []
    for payload in payloads:
        if isinstance(payload, CutPayload):
            parts.append("✂cut")
        elif isinstance(payload, GitChangePayload):
            diff = payload.diff_summary
            parts.append(f"git:{payload.branch} +{diff.insertions}/-{diff.deletions}")
        elif isinstance(payload, TransitionPayload):
            parts.append(payload.type)
            if full and payload.content:
                import json
                parts.append(json.dumps(payload.content)[:60])
    return " ".join(parts) if parts else "transition"


def render_outline(handle: RunHandle, opts: DumpOptions) -> str:
    graph = handle.run_graph
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_transition_ids(graph)
    root_id = opts.node_id or handle.root_node_id

    lines = [
        (
            f"run={handle.run_id}  nodes={len(graph.nodes)}  "
            f"transitions={len(graph.transitions)}"
        ),
        "",
    ]
    visited_nodes: set[str] = set()
    visited_transitions: set[str] = set()

    # Count multi-input transitions for joins index.
    multi_input_trans = [
        tid for tid, t in graph.transitions.items() if len(t.input_node_ids) > 1
    ]

    def emit_node(node_id: str, prefix: str, is_last: bool, depth: int) -> None:
        cut = " ✂" if node_id in inactive_nodes else ""
        connector = "" if depth == 0 else ("└─" if is_last else "├─")
        if node_id in visited_nodes:
            lines.append(f"{prefix}{connector}↻ {node_id}{cut}")
            return
        visited_nodes.add(node_id)
        lines.append(f"{prefix}{connector}{node_id}{cut}")
        note = _node_summary(graph, node_id)
        child_prefix = prefix + ("  " if depth == 0 or is_last else "│ ")
        if note:
            lines.append(f"{child_prefix}note: {_truncate(note, 80)}")
        if opts.depth is not None and depth >= opts.depth:
            return
        transition_ids = graph.transitions_from_node(node_id)
        for index, transition_id in enumerate(transition_ids):
            t = graph.transitions[transition_id]
            # Only render as primary if this node is inputs[0].
            if t.input_node_ids and t.input_node_ids[0] != node_id:
                lines.append(
                    f"{child_prefix}▸ feeds {transition_id} (@{t.input_node_ids[0]})"
                )
                continue
            emit_transition(
                transition_id,
                child_prefix,
                index == len(transition_ids) - 1,
                depth + 1,
            )

    def emit_transition(transition_id: str, prefix: str, is_last: bool, depth: int) -> None:
        t = graph.transitions[transition_id]
        summary = _transition_summary(graph, transition_id, opts.full_payloads)
        cut = " ✂" if transition_id in inactive_trans else ""
        connector = "└─" if is_last else "├─"
        if transition_id in visited_transitions:
            lines.append(f"{prefix}{connector}↻ {transition_id}{cut}")
            return
        visited_transitions.add(transition_id)
        # Show extra inputs inline.
        extras = ""
        if len(t.input_node_ids) > 1:
            extras = " " + " ".join(f"(+{n})" for n in t.input_node_ids[1:])
        lines.append(f"{prefix}{connector}→ {transition_id}{cut}{extras}  {summary}")
        child_prefix = prefix + ("  " if is_last else "│ ")
        if t.output_node_id:
            emit_node(t.output_node_id, child_prefix, True, depth + 1)

    emit_node(root_id, "", True, 0)

    if len(multi_input_trans) >= 3:
        lines.append("")
        lines.append("joins:")
        for tid in multi_input_trans:
            t = graph.transitions[tid]
            lines.append(f"  {tid}: inputs={list(t.input_node_ids)}")

    return "\n".join(lines)


def render_mermaid(handle: RunHandle, opts: DumpOptions) -> str:
    graph = handle.run_graph
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_transition_ids(graph)
    lines = ["```mermaid", "flowchart TD"]
    for node_id in graph.nodes:
        label = "State"
        note = _node_summary(graph, node_id)
        if note:
            label = _truncate(note, 36).replace('"', "'")
        is_root = node_id == handle.root_node_id
        cls = "root" if is_root else "cut" if node_id in inactive_nodes else "state"
        lines.append(f'  {node_id}["{label}"]')
        if cls != "state":
            lines.append(f"  class {node_id} {cls}")

    for transition_id, t in graph.transitions.items():
        summary = _transition_summary(graph, transition_id, False)
        summary = _truncate(summary, 42).replace('"', "'")
        is_cut = transition_id in inactive_trans
        if t.output_node_id:
            for inp in t.input_node_ids:
                lines.append(f'  {inp} -->|"{summary}"| {t.output_node_id}')
        if is_cut:
            lines.append(f"  class {transition_id} cut")

    if inactive_nodes:
        lines.append(f"  class {','.join(sorted(inactive_nodes))} cut")
    lines.append("  classDef cut stroke:#999,stroke-dasharray: 4 4,color:#999")
    lines.append("  classDef root fill:#ffcc00,stroke:#1d4ed8")
    lines.append("```")
    return "\n".join(lines)


def dump(handle: RunHandle, fmt: str, opts: DumpOptions) -> str:
    if fmt == "outline":
        return render_outline(handle, opts)
    if fmt == "mermaid":
        return render_mermaid(handle, opts)
    raise ValueError(f"unknown dump format: {fmt!r}")
