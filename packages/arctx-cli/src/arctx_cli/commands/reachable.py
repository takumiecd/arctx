"""arctx CLI reachable command."""

from __future__ import annotations

import argparse
import json

from arctx_cli.context import resolve_store, resolve_run_id_from_args


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "reachable", help="Show active subgraph forward-reachable from a node"
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--from-node", required=True, dest="from_node")
    parser.add_argument("--include-records", action="store_true")
    parser.add_argument("--store-dir", default=None)
    return parser


def run_reachable_command(
    *,
    run_id: str,
    from_node: str | None,
    view_name: str | None,
    include_records: bool,
    store_dir: str,
) -> dict:
    if from_node is None:
        raise ValueError("from_node is required")
    if view_name is not None:
        raise ValueError("view_name is no longer supported")

    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    g = handle.run_graph

    root_node_id = from_node

    if root_node_id not in g.nodes:
        raise KeyError(f"unknown node_id: {root_node_id}")

    result: dict = {"root_node_id": root_node_id}
    reachable = g.reachable_from(root_node_id)
    result.update(reachable)

    if include_records:
        result["nodes"] = [g.nodes[nid].to_dict() for nid in reachable["node_ids"]]
        result["steps"] = [
            g.steps[tid].to_dict() for tid in reachable["step_ids"]
        ]
        result["payloads"] = [g.payloads[pl_id].to_dict() for pl_id in reachable["payload_ids"]]

    return result


def cli_reachable(args) -> int:
    result = run_reachable_command(
        run_id=resolve_run_id_from_args(args),
        from_node=args.from_node,
        view_name=None,
        include_records=args.include_records,
        store_dir=args.store_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
