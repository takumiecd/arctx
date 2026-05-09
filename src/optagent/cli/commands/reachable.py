"""optagent CLI reachable command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "reachable", help="Show active subgraph forward-reachable from a node or view"
    )
    parser.add_argument("--run", default=None)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--from-node", dest="from_node", default=None)
    group.add_argument("--view", dest="view_name", default=None)
    parser.add_argument("--include-records", action="store_true")
    parser.add_argument("--store-dir", default=".optagent/runs")
    return parser


def run_reachable_command(
    *,
    run_id: str,
    from_node: str | None,
    view_name: str | None,
    include_records: bool,
    store_dir: str,
) -> dict:
    if from_node is None and view_name is None:
        raise ValueError("either from_node or view_name is required")
    if from_node is not None and view_name is not None:
        raise ValueError("from_node and view_name are mutually exclusive")

    store = JsonlRunStore(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    g = handle.run_graph

    if view_name is not None:
        view = handle.view_show(view_name)
        root_node_id = view.root_node_id
    else:
        root_node_id = from_node

    if root_node_id not in g.nodes:
        raise KeyError(f"unknown node_id: {root_node_id}")

    result: dict = {"root_node_id": root_node_id}
    reachable = g.reachable_from(root_node_id)
    result.update(reachable)

    if include_records:
        result["nodes"] = [g.nodes[nid].to_dict() for nid in reachable["node_ids"]]
        result["input_transitions"] = [
            g.input_transitions[it_id].to_dict()
            for it_id in reachable["input_transition_ids"]
        ]
        result["output_transitions"] = [
            g.output_transitions[ot_id].to_dict()
            for ot_id in reachable["output_transition_ids"]
        ]
        result["payloads"] = [
            g.payloads[pl_id].to_dict() for pl_id in reachable["payload_ids"]
        ]

    return result


def cli_reachable(args) -> int:
    result = run_reachable_command(
        run_id=resolve_run_id_from_args(args),
        from_node=args.from_node,
        view_name=args.view_name,
        include_records=args.include_records,
        store_dir=args.store_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
