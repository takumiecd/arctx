"""Dump RunGraph as outline or mermaid."""

from __future__ import annotations

from dataclasses import dataclass

from arctx.core.cuts import inactive_node_ids, inactive_step_ids
from arctx.core.lanes import lane_edge_summaries, lane_membership
from arctx.core.run.handle import RunHandle
from arctx.core.run_graph import RunGraph
from arctx.core.schema.payloads import CutPayload, NodePayload, StepPayload, SummaryPayload


@dataclass
class DumpOptions:
    node_id: str | None = None
    depth: int | None = None
    full_payloads: bool = False
    expand_closed_lanes: bool = False
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


def _summary_text(summaries: tuple[SummaryPayload, ...]) -> str:
    if not summaries:
        return "no summary"
    text = " / ".join(s.text for s in summaries if s.text)
    return text or "summary"


def _closed_lane_label(
    handle: RunHandle,
    lane_id: str,
    node_count: int,
    step_count: int,
) -> str:
    lane = handle.run_graph.lanes.get(lane_id)
    label = lane.name if lane is not None and lane.name else lane_id
    summaries = lane_edge_summaries(
        handle.run_graph,
        lane_id,
        root_node_id=handle.root_node_id,
    )
    counts = f"{node_count} nodes, {step_count} steps"
    summary = _truncate(_summary_text(summaries), 100)
    return f"closed lane {label} ({counts})  {summary}"


def render_outline(handle: RunHandle, opts: DumpOptions) -> str:
    graph = handle.run_graph
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_step_ids(graph)
    membership = lane_membership(graph, root_node_id=handle.root_node_id)
    closed_lane_ids = {
        lane_id
        for lane_id, lane in graph.lanes.items()
        if lane.status == "closed"
    }
    closed_lane_groups = {group.lane_id: group for group in membership.groups}
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
    collapsed_lanes: set[str] = set()

    # Count multi-input steps for joins index.
    multi_input_trans = [
        tid for tid, t in graph.steps.items() if len(t.input_node_ids) > 1
    ]

    def emit_node(node_id: str, prefix: str, is_last: bool, depth: int) -> None:
        lane_id = membership.node_to_lane.get(node_id)
        if not opts.expand_closed_lanes and lane_id in closed_lane_ids:
            if lane_id not in collapsed_lanes:
                emit_closed_lane(lane_id, prefix, is_last, depth)
            return
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
        lane_id = membership.step_to_lane.get(step_id)
        if not opts.expand_closed_lanes and lane_id in closed_lane_ids:
            if lane_id not in collapsed_lanes:
                emit_closed_lane(lane_id, prefix, is_last, depth)
            return
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
        out = t.output_node_id
        if out:
            active = graph.step_to_node(out)
            defer = (
                out not in visited_nodes
                and step_id in inactive_trans
                and active is not None
                and active != step_id
                and active not in inactive_trans
            )
            if defer:
                # Re-parented node: its live lineage hangs under the active
                # producer. Anchor the subtree there, not under this cut step.
                ncut = " ✂" if out in inactive_nodes else ""
                lines.append(
                    f"{child_prefix}└─↻ {out}{ncut} ▸ active producer {active}"
                )
            else:
                emit_node(out, child_prefix, True, depth + 1)

    def emit_closed_lane(lane_id: str, prefix: str, is_last: bool, depth: int) -> None:
        group = closed_lane_groups.get(lane_id)
        node_ids = tuple(group.node_ids) if group is not None else ()
        step_ids = tuple(group.step_ids) if group is not None else ()
        collapsed_lanes.add(lane_id)
        visited_nodes.update(node_ids)
        visited_steps.update(step_ids)
        connector = "" if depth == 0 else ("└─" if is_last else "├─")
        lines.append(
            f"{prefix}{connector}↧ {_closed_lane_label(handle, lane_id, len(node_ids), len(step_ids))}"
        )
        if opts.depth is not None and depth >= opts.depth:
            return
        child_prefix = prefix + ("  " if depth == 0 or is_last else "│ ")
        boundary_steps = tuple(
            dict.fromkeys(
                step_id
                for node_id in node_ids
                for step_id in graph.steps_from_node(node_id)
                if membership.step_to_lane.get(step_id) != lane_id
            )
        )
        for index, step_id in enumerate(boundary_steps):
            emit_step(
                step_id,
                child_prefix,
                index == len(boundary_steps) - 1,
                depth + 1,
            )

    emit_node(root_id, "", True, 0)

    orphan_starts = [
        node_id
        for node_id in graph.roots()
        if node_id != root_id and node_id not in visited_nodes
    ]
    orphan_starts += [
        node_id
        for node_id in graph.nodes
        if node_id not in visited_nodes and node_id not in orphan_starts
    ]
    if orphan_starts:
        lines.append("")
        lines.append("orphans:")
        for index, node_id in enumerate(orphan_starts):
            emit_node(node_id, "  ", index == len(orphan_starts) - 1, 0)

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
    membership = lane_membership(graph, root_node_id=handle.root_node_id)
    closed_lane_ids = {
        lane_id
        for lane_id, lane in graph.lanes.items()
        if lane.status == "closed"
    }
    hidden_nodes: set[str] = set()
    hidden_steps: set[str] = set()
    if not opts.expand_closed_lanes:
        for group in membership.groups:
            if group.lane_id in closed_lane_ids:
                hidden_nodes.update(group.node_ids)
                hidden_steps.update(group.step_ids)
    lines = ["```mermaid", "flowchart TD"]
    for node_id in graph.nodes:
        if node_id in hidden_nodes:
            continue
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
        if step_id in hidden_steps:
            continue
        summary = _step_summary(graph, step_id, False)
        summary = _truncate(summary, 42).replace('"', "'")
        is_cut = step_id in inactive_trans
        if t.output_node_id:
            for inp in t.input_node_ids:
                lines.append(f'  {inp} -->|"{summary}"| {t.output_node_id}')
        if is_cut:
            lines.append(f"  class {step_id} cut")

    if inactive_nodes:
        shown_inactive_nodes = sorted(inactive_nodes - hidden_nodes)
        if shown_inactive_nodes:
            lines.append(f"  class {','.join(shown_inactive_nodes)} cut")
    if not opts.expand_closed_lanes:
        for group in membership.groups:
            if group.lane_id not in closed_lane_ids:
                continue
            node_id = f"lane_{group.lane_id.replace('-', '_').replace('.', '_')}"
            label = _closed_lane_label(
                handle,
                group.lane_id,
                len(group.node_ids),
                len(group.step_ids),
            )
            label = _truncate(label, 64).replace('"', "'")
            lines.append(f'  {node_id}["{label}"]')
            lines.append(f"  class {node_id} closed")
            inputs = {
                input_node_id
                for step_id in group.step_ids
                for input_node_id in graph.steps[step_id].input_node_ids
                if input_node_id not in hidden_nodes
            }
            for input_node_id in sorted(inputs):
                lines.append(f"  {input_node_id} --> {node_id}")
    lines.append("  classDef cut stroke:#999,stroke-dasharray: 4 4,color:#999")
    lines.append("  classDef closed stroke:#777,stroke-dasharray: 2 3,color:#777")
    lines.append("  classDef root fill:#ffcc00,stroke:#1d4ed8")
    lines.append("```")
    return "\n".join(lines)


def dump(handle: RunHandle, fmt: str, opts: DumpOptions) -> str:
    if fmt == "outline":
        return render_outline(handle, opts)
    if fmt == "mermaid":
        return render_mermaid(handle, opts)
    raise ValueError(f"unknown dump format: {fmt!r}")
