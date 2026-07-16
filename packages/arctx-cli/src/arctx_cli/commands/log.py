"""User-facing arctx log command.

Plain ``arctx log`` renders a flat CHRONOLOGICAL listing of the run, oldest
first, like ``git log --oneline``: one line per recorded work event (step
creation, payload attachment, ...), each showing its ``seq``, timestamp, lane,
user, and a human title. ``WorkEvent`` rows carry the chronology (``seq`` /
``created_at``); the graph records themselves (nodes/steps/payloads) carry no
timestamps.

``--lanes`` renders a lane timeline instead: one line per lane ordered by
``started_at``, showing when it opened/closed and the first line of its close
summary, if any -- the "table of contents" for a run's phases.

``--outline`` (and ``--to``/legacy behavior) keeps the previous outline
dump / trace passthrough available for existing scripts.
"""

from __future__ import annotations

import argparse
import json

from arctx_cli.commands.dump import run_dump_command
from arctx_cli.commands.trace import run_trace_command
from arctx_cli.context import resolve_run_id_from_args, resolve_store


DEFAULT_LIMIT = 200


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("log", help="Show the run's chronological history")
    parser.add_argument("--from", dest="from_node", default=None, metavar="NODE_ID")
    parser.add_argument("--to", dest="to_node", default=None, metavar="NODE_ID")
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--full-payloads", action="store_true")
    parser.add_argument(
        "--from-summary",
        action="store_true",
        help="With --to, stop the backward walk at the nearest summary node",
    )
    parser.add_argument(
        "--outline",
        action="store_true",
        help="Render the previous outline-dump view instead of the chronological log",
    )
    parser.add_argument(
        "--lanes",
        action="store_true",
        help="Render a lane timeline (phase table of contents) instead of per-record events",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max number of rows to show (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Show newest first instead of oldest first",
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    return parser


# ---------------------------------------------------------------------------
# Chronological (work-event) rendering
# ---------------------------------------------------------------------------


def _truncate(s: str | None, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[: n - 1] + "…"


def _record_title(handle, record_id: str | None) -> str | None:
    """Best-effort human title for a created record, sharing dump.py's sources."""
    if not record_id:
        return None
    graph = handle.run_graph
    from arctx.core.run.dump import _node_summary, _step_summary

    if record_id in graph.steps:
        return _step_summary(graph, record_id, full=False)
    if record_id in graph.nodes:
        return _node_summary(graph, record_id)
    if record_id in graph.payloads:
        payload = graph.payloads[record_id]
        for attr in ("type", "title", "text"):
            val = getattr(payload, attr, None)
            if isinstance(val, str) and val:
                return val
        content = getattr(payload, "content", None)
        if isinstance(content, dict):
            title = content.get("title") or content.get("text")
            if isinstance(title, str) and title:
                return title
        return payload.payload_type
    return None


def _event_title(handle, event) -> str:
    """Human title for a work event: prefer a created record's title."""
    graph = handle.run_graph
    # Prefer step/node titles over payload ids among created_records.
    step_or_node = None
    payload_only = None
    for record_id in event.created_records:
        if record_id in graph.steps or record_id in graph.nodes:
            step_or_node = record_id
            break
        if payload_only is None and record_id in graph.payloads:
            payload_only = record_id
    title = _record_title(handle, step_or_node or payload_only)
    if title:
        return title
    if event.target_id:
        target_title = _record_title(handle, event.target_id)
        if target_title:
            return target_title
    if event.summary:
        return event.summary
    return event.event_type


def _lane_label(handle, lane_id: str | None) -> str:
    if not lane_id:
        return "(no lane)"
    lane = handle.run_graph.lanes.get(lane_id)
    if lane is None:
        return lane_id
    return lane.name or lane.lane_id


_NO_TIMESTAMP = "(no timestamp)  "


def _format_timestamp(created_at: str | None) -> str:
    if not created_at:
        return _NO_TIMESTAMP
    # created_at is an ISO-8601 string; render as "YYYY-MM-DD HH:MM".
    try:
        # Handle a trailing "Z" as well as "+00:00" offsets.
        text = created_at.replace("Z", "+00:00")
        from datetime import datetime

        dt = datetime.fromisoformat(text)
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return _truncate(created_at, 16)


def _event_row(handle, event) -> str:
    seq = event.seq if event.seq is not None else "-"
    ts = _format_timestamp(event.created_at)
    lane = _lane_label(handle, event.lane_id)
    user = event.user_id or "?"
    title = _truncate(_event_title(handle, event), 100)
    return f"[{seq}] {ts}  {lane:<20} {user:<12} {title}"


def render_chronological(handle, *, limit: int, reverse: bool) -> str:
    """Render a flat chronological listing built from work events, oldest first.

    ``handle.run_graph.work_events`` is itself in chronological (append) order:
    the jsonl store only ever appends rows, so file order already reflects
    write order even for the handful of events written by side paths (e.g. the
    git-hook ``amend`` bookkeeping) that predate ``seq``/``created_at`` being
    populated. Sorting by ``seq`` alone would incorrectly clump every
    ``seq is None`` event together, so list order is the source of truth and
    ``seq``/``created_at`` are used only for display.
    """
    # Lane overview maintenance has its own summary-first ``explore`` surface;
    # keep the default chronological log focused on graph work.
    events = [
        event
        for event in handle.run_graph.work_events
        if event.event_type != "lane_payload_attached"
    ]
    if not events:
        graph = handle.run_graph
        lines = [
            "(no work events recorded for this run; falling back to storage "
            "insertion order for nodes/steps)",
            "",
        ]
        for step_id in graph.steps:
            step = graph.steps[step_id]
            title = _record_title(handle, step_id) or "step"
            lines.append(f"[-] {step_id}  {_truncate(title, 100)}")
            if step.output_node_id:
                note = _record_title(handle, step.output_node_id)
                if note:
                    lines.append(f"      -> {step.output_node_id}  {_truncate(note, 100)}")
        if reverse:
            header, rest = lines[0], lines[1:]
            lines = [header, ""] + list(reversed(rest))
        if limit is not None and limit > 0:
            lines = lines[: limit + 2]
        return "\n".join(lines)

    ordered = events
    if reverse:
        ordered = list(reversed(ordered))
    if limit is not None and limit > 0:
        ordered = ordered[:limit]

    lines = [f"run={handle.run_id}  events={len(events)} (showing {len(ordered)})", ""]
    for event in ordered:
        lines.append(_event_row(handle, event))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Lane timeline rendering
# ---------------------------------------------------------------------------


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    return text.strip().splitlines()[0] if text.strip() else ""


def _lane_close_summary(handle, lane_id: str) -> str | None:
    from arctx.core.lanes import lane_edge_summaries

    summaries = lane_edge_summaries(
        handle.run_graph,
        lane_id,
        root_node_id=handle.root_node_id,
        active_only=False,
    )
    if not summaries:
        return None
    texts = [s.text for s in summaries if s.text]
    return " / ".join(texts) if texts else None


def render_lanes(handle, *, limit: int, reverse: bool) -> str:
    """Render one line per lane, ordered by started_at -- the phase timeline."""
    lanes = list(handle.run_graph.lanes.values())
    lanes.sort(key=lambda lane: (lane.started_at or "", lane.lane_id))
    if reverse:
        lanes = list(reversed(lanes))
    if limit is not None and limit > 0:
        lanes = lanes[:limit]

    lines = [f"run={handle.run_id}  lanes={len(handle.run_graph.lanes)} (showing {len(lanes)})", ""]
    for lane in lanes:
        name = lane.name or lane.lane_id
        started = _format_timestamp(lane.started_at)
        closed = _format_timestamp(lane.closed_at) if lane.closed_at else "open"
        summary = _first_line(_lane_close_summary(handle, lane.lane_id))
        row = f"{name:<24} {started} -> {closed:<16} {lane.created_by or '?'}"
        if summary:
            row += f"  {_truncate(summary, 80)}"
        lines.append(row)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command entry points
# ---------------------------------------------------------------------------


def run_log_command(
    *,
    run_id: str,
    from_node_id: str | None,
    to_node_id: str | None,
    depth: int | None,
    full_payloads: bool,
    store_dir: str,
    stop_at_summary: bool = False,
    outline: bool = False,
    lanes: bool = False,
    limit: int = DEFAULT_LIMIT,
    reverse: bool = False,
) -> dict:
    if from_node_id is not None and to_node_id is not None:
        raise ValueError("--from and --to are mutually exclusive")
    if stop_at_summary and to_node_id is None:
        raise ValueError("--from-summary requires --to")

    if to_node_id is not None:
        return run_trace_command(
            run_id=run_id,
            from_node_id=to_node_id,
            depth=depth,
            store_dir=store_dir,
            stop_at_summary=stop_at_summary,
        )

    if outline or from_node_id is not None or depth is not None or full_payloads:
        rendered = run_dump_command(
            run_id=run_id,
            fmt="outline",
            store_dir=store_dir,
            node_id=from_node_id,
            depth=depth,
            full_payloads=full_payloads,
        )
        return {"log": rendered}

    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    if lanes:
        return {"log": render_lanes(handle, limit=limit, reverse=reverse)}
    return {"log": render_chronological(handle, limit=limit, reverse=reverse)}


def cli_log(args) -> int:
    result = run_log_command(
        run_id=resolve_run_id_from_args(args),
        from_node_id=args.from_node,
        to_node_id=args.to_node,
        depth=args.depth,
        full_payloads=args.full_payloads,
        store_dir=args.store_dir,
        stop_at_summary=args.from_summary,
        outline=args.outline,
        lanes=args.lanes,
        limit=args.limit,
        reverse=args.reverse,
    )
    if "log" in result:
        print(result["log"])
    else:
        print(json.dumps(result["history"], ensure_ascii=False, indent=2))
    return 0
