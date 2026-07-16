"""Collapsed, summary-first traversal of the Lane DAG."""

from __future__ import annotations

import argparse
import json

from arctx.core.lanes import lane_membership, lane_overview, lane_roots

from arctx_cli.context import resolve_run_id_from_args, resolve_store


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the summary-first exploration command."""
    parser = subparsers.add_parser(
        "explore",
        help="Explore the Lane DAG one collapsed summary level at a time",
    )
    parser.add_argument("lane", nargs="?", help="Lane name/id; omit for DAG roots")
    parser.add_argument(
        "--depth", type=int, default=1,
        help="Number of child-lane levels to expand (default: 1)",
    )
    parser.add_argument(
        "--contents", action="store_true",
        help="Include direct Node/Step/Payload membership counts",
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


def _direct_counts(membership, lane_id: str) -> dict[str, int]:
    return {
        "nodes": sum(1 for owner in membership.node_to_lane.values() if owner == lane_id),
        "steps": sum(1 for owner in membership.step_to_lane.values() if owner == lane_id),
        "payloads": sum(
            1 for owner in membership.payload_to_lane.values() if owner == lane_id
        ),
    }


def _explore_item(
    handle, lane_id: str, *, depth: int, contents: bool,
    membership, path: tuple[str, ...], expanded: set[str],
) -> dict:
    """Return a bounded-depth collapsed projection of the Lane DAG."""
    overview = lane_overview(handle.run_graph, lane_id)
    item = overview.to_dict()
    item["shared"] = lane_id in expanded
    if contents:
        item["direct_counts"] = _direct_counts(membership, lane_id)
    if depth <= 0 or lane_id in path or lane_id in expanded:
        item["children"] = []
        return item
    expanded.add(lane_id)
    item["children"] = [
        _explore_item(
            handle,
            child_id,
            depth=depth - 1,
            contents=contents,
            membership=membership,
            path=path + (lane_id,),
            expanded=expanded,
        )
        for child_id in overview.child_lane_ids
    ]
    return item


def run_explore_command(
    *, run_id: str, store_dir: str | None, lane_name_or_id: str | None = None,
    depth: int = 1, contents: bool = False,
) -> dict:
    if depth < 0:
        raise ValueError("--depth must be >= 0")
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    if lane_name_or_id is None:
        root_ids = lane_roots(handle.run_graph)
    else:
        lane = _find_lane(handle, lane_name_or_id)
        if lane is None:
            raise KeyError(f"unknown lane: {lane_name_or_id!r}")
        root_ids = (lane.lane_id,)
    membership = lane_membership(handle.run_graph, root_node_id=handle.root_node_id)
    expanded: set[str] = set()
    return {
        "run_id": run_id,
        "depth": depth,
        "lanes": [
            _explore_item(
                handle,
                lane_id,
                depth=depth,
                contents=contents,
                membership=membership,
                path=(),
                expanded=expanded,
            )
            for lane_id in root_ids
        ],
    }


def _payload_text(payload: dict | None) -> str:
    if not payload:
        return "(summary missing)"
    content = payload.get("content") or {}
    return str(content.get("text") or "(empty summary)")


def _render_item(item: dict, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    marker = "↻" if item.get("shared") else "▸"
    name = item.get("name") or item["lane_id"]
    status = item.get("status", "open")
    stale = item.get("stale_child_lane_ids") or []
    suffix = f" [{status}]"
    if stale:
        suffix += f" [stale:{len(stale)}]"
    lines = [f"{prefix}{marker} {name}{suffix}"]
    summary = (item.get("current_values") or {}).get("summary")
    lines.append(f"{prefix}  {_payload_text(summary)}")
    if "direct_counts" in item:
        counts = item["direct_counts"]
        lines.append(
            f"{prefix}  {counts['nodes']} nodes / {counts['steps']} steps / "
            f"{counts['payloads']} graph payloads"
        )
    for child in item.get("children") or []:
        lines.extend(_render_item(child, indent + 1))
    return lines


def cli_explore(args) -> int:
    """Render a Lane exploration as text or JSON."""
    try:
        result = run_explore_command(
            run_id=resolve_run_id_from_args(args),
            store_dir=args.store_dir,
            lane_name_or_id=args.lane,
            depth=args.depth,
            contents=args.contents,
        )
        if args.as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif not result["lanes"]:
            print("(no lanes)")
        else:
            lines: list[str] = []
            for lane in result["lanes"]:
                lines.extend(_render_item(lane))
            print("\n".join(lines))
        return 0
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 2
