"""Dump RunGraph as outline or mermaid."""

from __future__ import annotations

from dataclasses import dataclass

from arctx.core.cuts import inactive_node_ids, inactive_step_ids
from arctx.core.run.handle import RunHandle
from arctx.core.run_graph import RunGraph
from arctx.core.schema.payloads import CutPayload, NodePayload, StepPayload


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
            title = payload.content.get("title")
            if isinstance(title, str) and title:
                return title
            return payload.type
    return None


def _step_summary(graph: RunGraph, step_id: str, full: bool) -> str:
    payloads = graph.payloads_for_step(step_id)
    parts = []
    for payload in payloads:
        if isinstance(payload, CutPayload):
            parts.append("✂cut")
        elif isinstance(payload, StepPayload):
            title = payload.content.get("title")
            text = payload.content.get("text")
            if isinstance(title, str) and title:
                parts.append(title)
            elif isinstance(text, str) and text:
                parts.append(text)
            else:
                parts.append(payload.type)
            if full and payload.content:
                import json
                parts.append(json.dumps(payload.content)[:60])
        else:
            parts.append(payload.payload_type)
    return " ".join(parts) if parts else "step"


def render_outline(handle: RunHandle, opts: DumpOptions) -> str:
    graph = handle.run_graph
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_step_ids(graph)
    root_id = opts.node_id or handle.root_node_id

    lines = [
        (
            f"run={handle.run_id}  nodes={len(graph.nodes)}  "
            f"steps={len(graph.steps)}"
        ),
        "",
    ]
    visited_nodes: set[str] = set()
    visited_steps: set[str] = set()

    # Count multi-input steps for joins index.
    multi_input_trans = [
        tid for tid, t in graph.steps.items() if len(t.input_node_ids) > 1
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
        step_ids = graph.steps_from_node(node_id)
        for index, step_id in enumerate(step_ids):
            t = graph.steps[step_id]
            # Only render as primary if this node is inputs[0].
            if t.input_node_ids and t.input_node_ids[0] != node_id:
                lines.append(
                    f"{child_prefix}▸ feeds {step_id} (@{t.input_node_ids[0]})"
                )
                continue
            emit_step(
                step_id,
                child_prefix,
                index == len(step_ids) - 1,
                depth + 1,
            )

    def emit_step(step_id: str, prefix: str, is_last: bool, depth: int) -> None:
        t = graph.steps[step_id]
        summary = _step_summary(graph, step_id, opts.full_payloads)
        cut = " ✂" if step_id in inactive_trans else ""
        connector = "└─" if is_last else "├─"
        if step_id in visited_steps:
            lines.append(f"{prefix}{connector}↻ {step_id}{cut}")
            return
        visited_steps.add(step_id)
        # Show extra inputs inline.
        extras = ""
        if len(t.input_node_ids) > 1:
            extras = " " + " ".join(f"(+{n})" for n in t.input_node_ids[1:])
        lines.append(f"{prefix}{connector}→ {step_id}{cut}{extras}  {summary}")
        child_prefix = prefix + ("  " if is_last else "│ ")
        if t.output_node_id:
            emit_node(t.output_node_id, child_prefix, True, depth + 1)

    emit_node(root_id, "", True, 0)

    if len(multi_input_trans) >= 3:
        lines.append("")
        lines.append("joins:")
        for tid in multi_input_trans:
            t = graph.steps[tid]
            lines.append(f"  {tid}: inputs={list(t.input_node_ids)}")

    return "\n".join(lines)


def render_mermaid(handle: RunHandle, opts: DumpOptions) -> str:
    graph = handle.run_graph
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_step_ids(graph)
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

    for step_id, t in graph.steps.items():
        summary = _step_summary(graph, step_id, False)
        summary = _truncate(summary, 42).replace('"', "'")
        is_cut = step_id in inactive_trans
        if t.output_node_id:
            for inp in t.input_node_ids:
                lines.append(f'  {inp} -->|"{summary}"| {t.output_node_id}')
        if is_cut:
            lines.append(f"  class {step_id} cut")

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
