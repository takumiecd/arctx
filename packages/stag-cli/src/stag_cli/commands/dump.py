"""stag CLI dump command: render a run as outline or mermaid."""

from __future__ import annotations

import argparse

from stag_cli.context import resolve_store, resolve_run_id_from_args
from stag_api.core.run.dump import DumpOptions, dump


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
    parser.add_argument("--store-dir", default=None)
    return parser


def run_dump_command(
    *,
    run_id: str,
    fmt: str = "outline",
    store_dir: str = ".stag/runs",
    node_id: str | None = None,
    depth: int | None = None,
    full_payloads: bool = False,
) -> str:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    opts = DumpOptions(node_id=node_id, depth=depth, full_payloads=full_payloads)
    return dump(handle, fmt, opts)


def cli_dump(args) -> int:
    if args.observed_only and args.predicted_only:
        raise ValueError("--observed-only and --predicted-only are mutually exclusive")
    store = resolve_store(args.store_dir)
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
