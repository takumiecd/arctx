"""arctx CLI export command: render a run as markdown, LaTeX, or HTML.

Unlike ``dump`` (inspection / LLM), ``export`` produces a standalone document
to share. By default it strips machine-local data (repo ``local_path``); pass
``--include-local`` to keep it. ``--exclude-cut`` drops cut history.
"""

from __future__ import annotations

import argparse

from arctx.core.run.export import ExportOptions, export
from arctx_cli.context import resolve_run_id_from_args, resolve_store


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "export",
        help="Export the run as a shareable document (md / tex / html)",
    )
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=["md", "tex", "html"],
        default="md",
        help="Output format (default: md)",
    )
    parser.add_argument("--node", dest="node_id", default=None,
                        help="Export only the subtree rooted at this node")
    parser.add_argument("--depth", type=int, default=None,
                        help="Limit traversal depth")
    parser.add_argument("--full-payloads", action="store_true",
                        help="Include full payload content")
    parser.add_argument("--exclude-cut", action="store_true",
                        help="Drop cut (inactive) nodes and steps")
    parser.add_argument("--include-local", action="store_true",
                        help="Keep repo local_path in the output (off by default)")
    parser.add_argument("--output", "-o", default=None,
                        help="Write to this file instead of stdout")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    return parser


def cli_export(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    opts = ExportOptions(
        node_id=args.node_id,
        depth=args.depth,
        full_payloads=args.full_payloads,
        exclude_cut=args.exclude_cut,
        include_local=args.include_local,
    )
    text = export(handle, args.fmt, opts)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0
