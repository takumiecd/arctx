"""optagent CLI dump command: render a run as outline or mermaid."""

from __future__ import annotations

import argparse

from optagent.cli.context import resolve_run_id_from_args
from optagent.core.run.dump import DumpOptions, dump
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "dump",
        help="Render the run as an outline (LLM-friendly) or mermaid (visual)",
    )
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=["outline", "mermaid"],
        default="outline",
        help="Output format (default: outline)",
    )
    parser.add_argument("--node", dest="node_id", default=None,
                        help="Render only the subtree rooted at this node")
    parser.add_argument("--depth", type=int, default=None,
                        help="Limit traversal depth")
    parser.add_argument("--observed-only", action="store_true",
                        help="Hide predicted output transitions")
    parser.add_argument("--predicted-only", action="store_true",
                        help="Hide observed (result) output transitions")
    parser.add_argument("--full-payloads", action="store_true",
                        help="Include full payload metrics / rationale")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=".optagent/runs")
    return parser


def cli_dump(args) -> int:
    if args.observed_only and args.predicted_only:
        raise ValueError("--observed-only and --predicted-only are mutually exclusive")
    store = JsonlRunStore(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    opts = DumpOptions(
        node_id=args.node_id,
        depth=args.depth,
        observed_only=args.observed_only,
        predicted_only=args.predicted_only,
        full_payloads=args.full_payloads,
    )
    print(dump(handle, args.fmt, opts))
    return 0
