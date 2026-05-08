"""optagent CLI trace command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("trace", help="Trace observed history from a node")
    parser.add_argument("--run", default=None)
    parser.add_argument("--from-node", required=True)
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--include-predictions", action="store_true")
    parser.add_argument("--store-dir", default=".optagent/runs")
    return parser


def run_trace_command(
    *,
    run_id: str,
    from_node_id: str,
    depth: int | None,
    include_predictions: bool = False,
    store_dir: str,
) -> dict:
    store = JsonlRunStore(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    history = handle.trace(
        from_node_id,
        depth=depth,
        include_predictions=include_predictions,
    )
    return {"history": history.to_dict()}


def cli_trace(args) -> int:
    result = run_trace_command(
        run_id=resolve_run_id_from_args(args),
        from_node_id=args.from_node,
        depth=args.depth,
        include_predictions=args.include_predictions,
        store_dir=args.store_dir,
    )
    print(json.dumps(result["history"], ensure_ascii=False, indent=2))
    return 0
