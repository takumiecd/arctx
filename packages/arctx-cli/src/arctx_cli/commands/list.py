"""arctx CLI list command."""

from __future__ import annotations

import argparse
import json

from arctx_cli.context import resolve_store


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``list`` subcommand parser."""
    parser = subparsers.add_parser("list", help="List saved runs")
    parser.add_argument(
        "--store-dir",
        default=None,
        help="Directory where runs are stored (default: .arctx/runs)",
    )
    return parser


def run_list_command(*, store_dir: str) -> dict:
    """List all runs in the store directory.

    Parameters
    ----------
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with ``runs`` key containing a list of run summary dicts.
    """
    store = resolve_store(store_dir)
    return {"runs": store.list_runs()}


def cli_list(args) -> int:
    """Entry point for ``arctx list`` subcommand.

    Prints the list of runs as JSON to stdout.
    """
    result = run_list_command(store_dir=args.store_dir)
    print(json.dumps(result["runs"], ensure_ascii=False, indent=2))
    return 0
