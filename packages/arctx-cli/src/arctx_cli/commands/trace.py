"""arctx CLI trace command."""

from __future__ import annotations

import argparse
import json

from arctx_cli.context import resolve_store, resolve_run_id_from_args


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("trace", help="Trace observed history from a node")
    parser.add_argument("--run", default=None)
    parser.add_argument("--from-node", required=True)
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--store-dir", default=None)
    return parser


def run_trace_command(
    *,
    run_id: str,
    from_node_id: str,
    depth: int | None,
    store_dir: str,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    history = handle.trace(
        from_node_id,
        depth=depth,
    )
    return {"history": history.to_dict()}


def cli_trace(args) -> int:
    result = run_trace_command(
        run_id=resolve_run_id_from_args(args),
        from_node_id=args.from_node,
        depth=args.depth,
        store_dir=args.store_dir,
    )
    print(json.dumps(result["history"], ensure_ascii=False, indent=2))
    return 0
