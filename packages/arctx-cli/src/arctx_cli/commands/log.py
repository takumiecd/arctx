"""User-facing arctx log command."""

from __future__ import annotations

import argparse
import json

from arctx_cli.commands.dump import run_dump_command
from arctx_cli.commands.trace import run_trace_command
from arctx_cli.context import resolve_run_id_from_args


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("log", help="Show the DAG history")
    parser.add_argument("--from", dest="from_node", default=None, metavar="NODE_ID")
    parser.add_argument("--to", dest="to_node", default=None, metavar="NODE_ID")
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--full-payloads", action="store_true")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    return parser


def run_log_command(
    *,
    run_id: str,
    from_node_id: str | None,
    to_node_id: str | None,
    depth: int | None,
    full_payloads: bool,
    store_dir: str,
) -> dict:
    if from_node_id is not None and to_node_id is not None:
        raise ValueError("--from and --to are mutually exclusive")
    if to_node_id is not None:
        return run_trace_command(
            run_id=run_id,
            from_node_id=to_node_id,
            depth=depth,
            store_dir=store_dir,
        )
    rendered = run_dump_command(
        run_id=run_id,
        fmt="outline",
        store_dir=store_dir,
        node_id=from_node_id,
        depth=depth,
        full_payloads=full_payloads,
    )
    return {"log": rendered}


def cli_log(args) -> int:
    result = run_log_command(
        run_id=resolve_run_id_from_args(args),
        from_node_id=args.from_node,
        to_node_id=args.to_node,
        depth=args.depth,
        full_payloads=args.full_payloads,
        store_dir=args.store_dir,
    )
    if "log" in result:
        print(result["log"])
    else:
        print(json.dumps(result["history"], ensure_ascii=False, indent=2))
    return 0
