"""stag node commands."""

from __future__ import annotations

import argparse
import json

from stag_cli.commands.show import run_show_command
from stag_cli.context import resolve_run_id_from_args


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("node", help="Inspect nodes")
    node_sub = parser.add_subparsers(dest="node_command", required=True)

    sp_show = node_sub.add_parser("show", help="Show one node")
    sp_show.add_argument("node_id")
    sp_show.add_argument("--with-payloads", action="store_true")
    sp_show.add_argument("--run", default=None)
    sp_show.add_argument("--store-dir", default=None)

    sp_payloads = node_sub.add_parser("payloads", help="Show node payloads")
    sp_payloads.add_argument("node_id")
    sp_payloads.add_argument("--run", default=None)
    sp_payloads.add_argument("--store-dir", default=None)

    return parser


def cli_node(args) -> int:
    if args.node_command == "show":
        result = run_show_command(
            run_id=resolve_run_id_from_args(args),
            node_id=args.node_id,
            transition_id=None,
            payload_id=None,
            with_payloads=args.with_payloads,
            outputs=False,
            store_dir=args.store_dir,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.node_command == "payloads":
        result = run_show_command(
            run_id=resolve_run_id_from_args(args),
            node_id=args.node_id,
            transition_id=None,
            payload_id=None,
            with_payloads=True,
            outputs=False,
            store_dir=args.store_dir,
        )
        print(json.dumps(result["payloads"], ensure_ascii=False, indent=2))
        return 0
    return 1
