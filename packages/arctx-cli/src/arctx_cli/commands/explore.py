"""arctx CLI ``explore`` — flat, summary-first retrieval over lanes.

Lanes are flat (git-branch-like), so there is nothing to descend. ``explore``
answers two of the three retrieval questions:

- ``arctx explore``            — what lanes exist (open first, closed folded)
- ``arctx explore <LANE>``     — what happened in this lane
- ``arctx explore --query ...`` — what has been tried about X (the primary path)

Search is position-independent: it needs no current lane and no traversal, and
every hit carries the record/payload ids to jump to with ``arctx show``.
"""

from __future__ import annotations

import argparse
import json
import sys

from arctx.core.lanes import (
    collapse_summary,
    lane_overview,
    list_lane_overviews,
    search_lanes,
)

from arctx_cli.context import resolve_run_id_from_args, resolve_store


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``explore`` command."""
    parser = subparsers.add_parser(
        "explore",
        help="List lanes, show one lane, or search the run (flat, summary-first)",
        description=(
            "No args: one line per lane (open lanes first; closed lanes folded "
            "into a count unless --all). LANE: that lane's overview. "
            "--query TERMS: case-insensitive AND search across lane names and "
            "the payloads each lane owns."
        ),
    )
    parser.add_argument("lane", nargs="?", help="Lane name or id to show in full")
    parser.add_argument(
        "-q",
        "--query",
        default=None,
        help="Search terms (AND, case-insensitive) across lanes and their payloads",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="show_all",
        help="Include closed lanes in the flat list instead of folding them",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    return parser


def _find_lane(handle, name_or_id: str):
    lane = handle.run_graph.lanes.get(name_or_id)
    if lane is not None:
        return lane
    return next(
        (item for item in handle.run_graph.lanes.values() if item.name == name_or_id),
        None,
    )


def _load(run_id: str, store_dir: str | None):
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    return store.load_run(run_id)


def run_explore_command(
    *,
    run_id: str,
    store_dir: str | None,
    lane_name_or_id: str | None = None,
    query: str | None = None,
    show_all: bool = False,
) -> dict:
    """Return the JSON-ready result for one of ``explore``'s three modes."""
    handle = _load(run_id, store_dir)
    graph = handle.run_graph
    root_node_id = handle.root_node_id

    if query:
        hits = search_lanes(graph, query, root_node_id=root_node_id)
        return {
            "run_id": run_id,
            "mode": "search",
            "query": query,
            "matches": [hit.to_dict() for hit in hits],
        }

    if lane_name_or_id is not None:
        lane = _find_lane(handle, lane_name_or_id)
        if lane is None:
            raise KeyError(f"unknown lane: {lane_name_or_id!r}")
        overview = lane_overview(graph, lane.lane_id, root_node_id=root_node_id)
        return {"run_id": run_id, "mode": "lane", "lane": overview.to_dict()}

    overviews = list_lane_overviews(graph, root_node_id=root_node_id)
    shown = [item for item in overviews if show_all or item.status == "open"]
    hidden = len(overviews) - len(shown)
    return {
        "run_id": run_id,
        "mode": "list",
        "lanes": [item.to_dict() for item in shown],
        "hidden_closed": hidden,
        "total": len(overviews),
    }


_STATUS_MARKER = {"open": "*", "closed": "-"}


def _render_list(result: dict) -> list[str]:
    lanes = result["lanes"]
    if not lanes and not result["hidden_closed"]:
        return ["(no lanes)"]
    lines = []
    for lane in lanes:
        marker = _STATUS_MARKER.get(lane["status"], "?")
        summary = lane["summary_line"] or "(no summary)"
        lines.append(f"{marker} {lane['label']}  {summary}")
    hidden = result["hidden_closed"]
    if hidden:
        noun = "lane" if hidden == 1 else "lanes"
        lines.append(f"{hidden} closed {noun} — use --all")
    return lines


def _render_lane(lane: dict) -> list[str]:
    marker = _STATUS_MARKER.get(lane["status"], "?")
    lines = [f"{marker} {lane['label']} [{lane['status']}]"]
    lines.append(f"  purpose: {lane['purpose'] or '(not recorded)'}")
    if lane["summary"]:
        lines.append(f"  summary ({lane['summary_payload_id']}):")
        lines.extend(f"    {line}" for line in lane["summary"].splitlines())
    else:
        lines.append("  summary: (none yet)")
    counts = lane["counts"]
    lines.append(
        f"  records: {counts['nodes']} nodes / {counts['steps']} steps / "
        f"{counts['payloads']} payloads"
    )
    frontiers = lane["active_frontier_node_ids"]
    lines.append(f"  active frontiers: {', '.join(frontiers) if frontiers else '(none)'}")
    return lines


def _render_search(result: dict) -> list[str]:
    matches = result["matches"]
    if not matches:
        return ["(no matching lanes)"]
    lines = []
    for match in matches:
        marker = _STATUS_MARKER.get(match["status"], "?")
        lines.append(f"{marker} {match['label']} [{match['status']}]")
        lines.append(f"  {match['snippet']}")
        jumps = match["matched_payload_ids"] or match["matched_record_ids"]
        if jumps:
            lines.append(f"  arctx show {' | '.join(jumps[:5])}")
    return lines


def render_explore(result: dict) -> str:
    """Render an ``explore`` result as agent-readable text."""
    mode = result["mode"]
    if mode == "search":
        return "\n".join(_render_search(result))
    if mode == "lane":
        return "\n".join(_render_lane(result["lane"]))
    return "\n".join(_render_list(result))


def cli_explore(args) -> int:
    """Dispatch ``explore``."""
    try:
        result = run_explore_command(
            run_id=resolve_run_id_from_args(args),
            store_dir=args.store_dir,
            lane_name_or_id=args.lane,
            query=args.query,
            show_all=getattr(args, "show_all", False),
        )
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_explore(result))
    return 0


__all__ = ["add_parser", "cli_explore", "collapse_summary", "run_explore_command"]
