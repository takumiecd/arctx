"""Dump RunGraph as outline (LLM-friendly) or mermaid (human-friendly).

Outline rules:
  - Each node and each transition appears exactly once (spanning tree).
  - Multi-input transitions: anchored under input_node_ids[0] (primary).
    Additional inputs annotated inline as "(+n_X)". Non-primary parents get
    a one-line forward pointer "feeds it_X (@n_primary)".
  - Cut nodes/transitions marked with "✂".
  - Predicted output transitions marked with "⇢", observed with "→".
  - Back-references to already-rendered nodes use "↻n_X".
"""

from __future__ import annotations

from dataclasses import dataclass

from stag.core.cuts import (
    inactive_input_transition_ids,
    inactive_node_ids,
    inactive_output_transition_ids,
)
from stag.core.run.handle import RunHandle
from stag.core.run_graph import RunGraph
from stag.core.schema.payloads import (
    GitChangePayload,
    NotePayload,
    PlanPayload,
    PredictionPayload,
    ResultPayload,
)


@dataclass
class DumpOptions:
    node_id: str | None = None
    depth: int | None = None
    observed_only: bool = False
    predicted_only: bool = False
    full_payloads: bool = False


# ---------- shared helpers ------------------------------------------------


def _plan_intent(graph: RunGraph, it_id: str) -> str:
    for p in graph.payloads_for_input_transition(it_id):
        if isinstance(p, PlanPayload):
            return p.intent
    return ""


def _node_note(graph: RunGraph, node_id: str) -> str | None:
    for p in graph.payloads_for_node(node_id):
        if isinstance(p, NotePayload):
            return p.text
    return None


def _ot_summary(graph: RunGraph, ot_id: str, full: bool) -> tuple[str, str]:
    """Return (kind_marker, summary_str) for an output transition.

    kind_marker is "→" (result), "⇢" (prediction), or "?" (unknown).
    """
    payloads = graph.payloads_for_output_transition(ot_id)

    # 1. Find GitChangePayload if any
    git_part = ""
    for p in payloads:
        if isinstance(p, GitChangePayload):
            summary = p.diff_summary
            files = ",".join(p.changed_files)
            if full:
                git_part = (
                    f"git:[{p.branch} {p.head_commit[:7]}] "
                    f"files_changed={summary.files_changed} "
                    f"(+{summary.insertions}/-{summary.deletions}) [{files}]"
                )
            else:
                git_part = f"git:(+{summary.insertions}/-{summary.deletions})"
                if p.changed_files:
                    git_part += f" [{files}]"
            break

    # 2. Find primary payload (Result or Prediction) and determine kind
    kind_marker = "?"
    primary_part = ""

    # Check ResultPayload first
    for p in payloads:
        if isinstance(p, ResultPayload):
            kind_marker = "→"
            parts: list[str] = [f"status={p.status}"]
            if p.metrics:
                metrics = (
                    " ".join(f"{k}={v}" for k, v in p.metrics.items())
                    if full
                    else _short_metrics(p.metrics)
                )
                parts.append(metrics)
            primary_part = " ".join(parts)
            break

    # If no ResultPayload, check PredictionPayload
    if kind_marker == "?":
        for p in payloads:
            if isinstance(p, PredictionPayload):
                kind_marker = "⇢"
                parts = []
                if p.predicted_metrics:
                    parts.append(_short_metrics(p.predicted_metrics))
                if p.rationale and full:
                    parts.append(f'"{p.rationale}"')
                primary_part = " ".join(parts)
                break

    # Combine primary_part and git_part
    combined_parts = []
    if primary_part:
        combined_parts.append(primary_part)
    if git_part:
        combined_parts.append(git_part)

    return kind_marker, "  ".join(combined_parts)


def _short_metrics(metrics: dict[str, float], limit: int = 3) -> str:
    items = list(metrics.items())[:limit]
    rendered = " ".join(f"{k}={_fmt_metric(v)}" for k, v in items)
    if len(metrics) > limit:
        rendered += f" (+{len(metrics) - limit} more)"
    return rendered


def _fmt_metric(v: float) -> str:
    if abs(v) >= 1000 or (v != 0 and abs(v) < 0.001):
        return f"{v:.3g}"
    return f"{v:g}"


def _truncate(s: str, n: int = 80) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _is_predicted_node(graph: RunGraph, node_id: str) -> bool:
    """A node is "predicted" if every incoming OT is a prediction."""
    incoming = graph.output_transitions_to_node.get(node_id, [])
    if not incoming:
        return False
    for ot_id in incoming:
        if graph.output_kind(ot_id) == "result":
            return False
    return True


# ---------- outline format -------------------------------------------------


def render_outline(handle: RunHandle, opts: DumpOptions) -> str:
    graph = handle.run_graph
    inactive_nodes = inactive_node_ids(graph)
    inactive_its = inactive_input_transition_ids(graph)
    inactive_ots = inactive_output_transition_ids(graph)

    # Determine traversal root
    root_id = opts.node_id or handle.root_node_id

    # Filter helpers
    def show_ot(ot_id: str) -> bool:
        kind = graph.output_kind(ot_id)
        if opts.observed_only and kind != "result":
            return False
        if opts.predicted_only and kind != "prediction":
            return False
        return True

    # Counters
    n_observed = sum(
        1 for nid in graph.nodes if nid not in inactive_nodes and not _is_predicted_node(graph, nid)
    )
    n_predicted = sum(
        1 for nid in graph.nodes if nid not in inactive_nodes and _is_predicted_node(graph, nid)
    )
    n_cut = len(inactive_nodes)

    # Joins index: ITs with len(input_node_ids) > 1
    joins: list[tuple[str, tuple[str, ...]]] = [
        (it_id, it.input_node_ids)
        for it_id, it in graph.input_transitions.items()
        if len(it.input_node_ids) > 1
    ]
    joins.sort()

    lines: list[str] = []

    # Header
    req = handle.requirement
    target = getattr(req, "target_id", None) or req.requirement_id
    lines.append(
        f"run={handle.run_id}  target={target}  "
        f"nodes={len(graph.nodes)}  its={len(graph.input_transitions)}  "
        f"ots={len(graph.output_transitions)}  "
        f"observed={n_observed}  predicted={n_predicted}" + (f"  cut={n_cut}" if n_cut else "")
    )

    # Joins index (only if ≥3)
    if len(joins) >= 3:
        lines.append(f"joins ({len(joins)}):")
        for it_id, inputs in joins:
            lines.append(f"  {it_id}  [{','.join(inputs)}]")

    lines.append("")

    # State for traversal
    visited_nodes: set[str] = set()
    visited_its: set[str] = set()

    def emit_node(node_id: str, prefix: str, is_last: bool, depth: int) -> None:
        if node_id not in graph.nodes:
            return

        cut_mark = " ✂" if node_id in inactive_nodes else ""
        role = "predicted" if _is_predicted_node(graph, node_id) else "observed"
        if opts.observed_only and role != "observed":
            return
        if opts.predicted_only and role != "predicted":
            return

        if node_id in visited_nodes:
            connector = "└─" if is_last else "├─"
            lines.append(f"{prefix}{connector} ↻{node_id}")
            return
        visited_nodes.add(node_id)

        if depth == 0:
            lines.append(
                f"{node_id}{cut_mark}  [root]"
                if node_id == handle.root_node_id
                else f"{node_id}{cut_mark}"
            )
        else:
            connector = "└─" if is_last else "├─"
            lines.append(f"{prefix}{connector} {node_id}{cut_mark}")

        # Note attached to node
        note = _node_note(graph, node_id)
        if note:
            note_prefix = prefix + ("    " if is_last else "│   ")
            lines.append(f"{note_prefix}▸ note: {_truncate(note, 100)}")

        # Recurse depth limit
        if opts.depth is not None and depth >= opts.depth:
            return

        # Outgoing ITs from this node — but only those where this node is primary
        child_its: list[str] = []
        forward_pointer_its: list[str] = []
        for it_id in graph.input_transitions_from_node.get(node_id, []):
            it = graph.input_transitions[it_id]
            if it.input_node_ids[0] == node_id:
                child_its.append(it_id)
            else:
                forward_pointer_its.append(it_id)

        # Order: observed-first (by smallest result OT id) then predicted-only
        def it_sort_key(it_id: str) -> tuple[int, str]:
            ots = graph.output_transitions_from_it.get(it_id, [])
            has_result = any(graph.output_kind(o) == "result" for o in ots)
            return (0 if has_result else 1, it_id)

        child_its.sort(key=it_sort_key)

        child_prefix = prefix + ("    " if (depth == 0 or is_last) else "│   ")

        # Forward pointers first (compact)
        for fp_it_id in forward_pointer_its:
            it = graph.input_transitions[fp_it_id]
            primary = it.input_node_ids[0]
            lines.append(f"{child_prefix}▸ feeds {fp_it_id} (@{primary})")

        n_children = len(child_its)
        for i, it_id in enumerate(child_its):
            emit_input_transition(it_id, child_prefix, i == n_children - 1, depth + 1)

    def emit_input_transition(it_id: str, prefix: str, is_last: bool, depth: int) -> None:
        if it_id in visited_its:
            return
        visited_its.add(it_id)

        it = graph.input_transitions[it_id]
        cut = it_id in inactive_its
        intent = _truncate(_plan_intent(graph, it_id), 80)
        extra_inputs = it.input_node_ids[1:]
        join_note = ""
        if extra_inputs:
            marks = []
            for nid in extra_inputs:
                pre = ""
                if nid in inactive_nodes:
                    pre = "✂"
                elif _is_predicted_node(graph, nid):
                    pre = "⇢"
                marks.append(f"{pre}{nid}")
            join_note = f" (+{' +'.join(marks)})"

        connector = "└─" if is_last else "├─"
        intent_s = f"  [{intent}]" if intent else ""
        cut_s = " ✂" if cut else ""
        lines.append(f"{prefix}{connector} {it_id}{join_note}{intent_s}{cut_s}")

        ot_prefix = prefix + ("    " if is_last else "│   ")

        # Outputs from this IT
        ot_ids = graph.output_transitions_from_it.get(it_id, [])
        # Filter
        ot_ids_visible = [o for o in ot_ids if show_ot(o)]
        ot_ids_visible.sort()
        # Order: results first
        ot_ids_visible.sort(key=lambda o: (0 if graph.output_kind(o) == "result" else 1, o))

        n_ots = len(ot_ids_visible)
        for j, ot_id in enumerate(ot_ids_visible):
            ot = graph.output_transitions[ot_id]
            kind_mark, summary = _ot_summary(graph, ot_id, opts.full_payloads)
            ot_cut = " ✂" if ot_id in inactive_ots else ""
            is_last_ot = j == n_ots - 1
            ot_connector = "└─" if is_last_ot else "├─"

            to_node = ot.to_node_id
            if to_node in visited_nodes:
                lines.append(
                    f"{ot_prefix}{ot_connector}{kind_mark} ↻{to_node}{ot_cut}"
                    + (f"  {summary}" if summary else "")
                )
                continue

            # Inline node line
            visited_nodes.add(to_node)
            cut_mark = " ✂" if to_node in inactive_nodes else ""
            head = f"{ot_prefix}{ot_connector}{kind_mark} {to_node}{cut_mark}"
            if summary:
                head += f"  {summary}"
            lines.append(head)

            note = _node_note(graph, to_node)
            sub_prefix = ot_prefix + ("    " if is_last_ot else "│   ")
            if note:
                lines.append(f"{sub_prefix}▸ note: {_truncate(note, 100)}")

            if opts.depth is not None and depth >= opts.depth:
                continue

            # Recurse from to_node (skip outer node-level header; emit ITs inline)
            child_its: list[str] = []
            forward_pointer_its: list[str] = []
            for sub_it_id in graph.input_transitions_from_node.get(to_node, []):
                sub_it = graph.input_transitions[sub_it_id]
                if sub_it.input_node_ids[0] == to_node:
                    child_its.append(sub_it_id)
                else:
                    forward_pointer_its.append(sub_it_id)

            def sk(it_id: str) -> tuple[int, str]:
                ots2 = graph.output_transitions_from_it.get(it_id, [])
                hr = any(graph.output_kind(o) == "result" for o in ots2)
                return (0 if hr else 1, it_id)

            child_its.sort(key=sk)

            for fp in forward_pointer_its:
                primary = graph.input_transitions[fp].input_node_ids[0]
                lines.append(f"{sub_prefix}▸ feeds {fp} (@{primary})")

            for k, sub_it in enumerate(child_its):
                emit_input_transition(sub_it, sub_prefix, k == len(child_its) - 1, depth + 1)

    emit_node(root_id, "", True, 0)

    # Orphan ITs (root-less or unvisited) — show under a dedicated section if any
    leftovers = [it for it in graph.input_transitions if it not in visited_its]
    if leftovers:
        lines.append("")
        lines.append("orphan transitions:")
        for it_id in sorted(leftovers):
            it = graph.input_transitions[it_id]
            intent = _truncate(_plan_intent(graph, it_id), 80)
            lines.append(f"  {it_id}  inputs={list(it.input_node_ids)}  [{intent}]")

    return "\n".join(lines)


# ---------- mermaid format -------------------------------------------------


def render_mermaid(handle: RunHandle, opts: DumpOptions) -> str:
    graph = handle.run_graph
    inactive_nodes = inactive_node_ids(graph)
    inactive_ots = inactive_output_transition_ids(graph)

    lines: list[str] = ["```mermaid", "flowchart TD"]

    # Style classes
    lines.append("    classDef observed fill:#dff5e1,stroke:#2a8540,color:#1a3a22;")
    lines.append(
        "    classDef predicted fill:#eef0fb,stroke:#5664c2,color:#22264a,stroke-dasharray: 4 3;"
    )
    lines.append(
        "    classDef cut fill:#f4e3e3,stroke:#a14040,color:#4a1d1d,stroke-dasharray: 2 2;"
    )
    lines.append("    classDef root fill:#fff5d6,stroke:#a07000,color:#3a2a00;")

    # Nodes
    for node_id in graph.nodes:
        label = node_id
        note = _node_note(graph, node_id)
        if note:
            label += "<br/>" + _truncate(note, 60).replace('"', "'")
        lines.append(f'    {node_id}["{label}"]')
        if node_id == handle.root_node_id:
            lines.append(f"    class {node_id} root;")
        elif node_id in inactive_nodes:
            lines.append(f"    class {node_id} cut;")
        elif _is_predicted_node(graph, node_id):
            lines.append(f"    class {node_id} predicted;")
        else:
            lines.append(f"    class {node_id} observed;")

    # Edges: render IT as intermediate diamond when it has multiple inputs or outputs
    for it_id, it in graph.input_transitions.items():
        intent = _truncate(_plan_intent(graph, it_id), 50).replace('"', "'")
        ots = graph.output_transitions_from_it.get(it_id, [])
        # Filter
        if opts.observed_only:
            ots = [o for o in ots if graph.output_kind(o) == "result"]
        if opts.predicted_only:
            ots = [o for o in ots if graph.output_kind(o) == "prediction"]

        multi_in = len(it.input_node_ids) > 1
        multi_out = len(ots) > 1

        if multi_in or multi_out:
            label = f"{it_id}: {intent}" if intent else it_id
            lines.append(f'    {it_id}{{{{"{label}"}}}}')
            for nid in it.input_node_ids:
                lines.append(f"    {nid} --> {it_id}")
            for ot_id in ots:
                ot = graph.output_transitions[ot_id]
                arrow = "-.->" if graph.output_kind(ot_id) == "prediction" else "-->"
                lines.append(f"    {it_id} {arrow} {ot.to_node_id}")
        else:
            # Direct edge: parent -[label]-> child
            if not ots:
                continue
            ot_id = ots[0]
            ot = graph.output_transitions[ot_id]
            arrow = "-.->" if graph.output_kind(ot_id) == "prediction" else "-->"
            label = intent or it_id
            parent = it.input_node_ids[0]
            cut_marker = " ✂" if ot_id in inactive_ots else ""
            lines.append(f'    {parent} {arrow}|"{label}{cut_marker}"| {ot.to_node_id}')

    lines.append("```")
    return "\n".join(lines)


# ---------- entry point ----------------------------------------------------


def dump(handle: RunHandle, fmt: str, opts: DumpOptions) -> str:
    if fmt == "outline":
        return render_outline(handle, opts)
    if fmt == "mermaid":
        return render_mermaid(handle, opts)
    raise ValueError(f"unknown format: {fmt!r}")
