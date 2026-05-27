"""arctx graph commands."""

from __future__ import annotations

import argparse
import json

from arctx_cli.commands.dump import run_dump_command
from arctx_cli.commands.reachable import run_reachable_command
from arctx_cli.commands.trace import run_trace_command
from arctx_cli.context import resolve_run_id_from_args


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("graph", help="Inspect graph structure")
    graph_sub = parser.add_subparsers(dest="graph_command", required=True)

    sp_dump = graph_sub.add_parser("dump", help="Render the graph")
    sp_dump.add_argument("--format", dest="fmt", choices=["outline", "mermaid"], default="outline")
    sp_dump.add_argument("--node", dest="node_id", default=None)
    sp_dump.add_argument("--depth", type=int, default=None)
    sp_dump.add_argument("--full-payloads", action="store_true")
    sp_dump.add_argument("--run", default=None)
    sp_dump.add_argument("--store-dir", default=None)

    sp_trace = graph_sub.add_parser("trace", help="Trace history from a node")
    sp_trace.add_argument("node_id")
    sp_trace.add_argument("--depth", type=int, default=None)
    sp_trace.add_argument("--run", default=None)
    sp_trace.add_argument("--store-dir", default=None)

    sp_reachable = graph_sub.add_parser("reachable", help="Show active graph forward from a node")
    sp_reachable.add_argument("node_id")
    sp_reachable.add_argument("--include-records", action="store_true")
    sp_reachable.add_argument("--run", default=None)
    sp_reachable.add_argument("--store-dir", default=None)

    return parser


def cli_graph(args) -> int:
    if args.graph_command == "dump":
        print(
            run_dump_command(
                run_id=resolve_run_id_from_args(args),
                fmt=args.fmt,
                store_dir=args.store_dir,
                node_id=args.node_id,
                depth=args.depth,
                full_payloads=args.full_payloads,
            )
        )
        return 0
    if args.graph_command == "trace":
        result = run_trace_command(
            run_id=resolve_run_id_from_args(args),
            from_node_id=args.node_id,
            depth=args.depth,
            store_dir=args.store_dir,
        )
        print(json.dumps(result["history"], ensure_ascii=False, indent=2))
        return 0
    if args.graph_command == "reachable":
        result = run_reachable_command(
            run_id=resolve_run_id_from_args(args),
            from_node=args.node_id,
            view_name=None,
            include_records=args.include_records,
            store_dir=args.store_dir,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 1
