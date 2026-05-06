"""optagent CLI current command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import load_current_run


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``current`` subcommand parser."""
    parser = subparsers.add_parser("current", help="Show the current run")
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    return parser


def run_current_command(
    *,
    store_dir: str,
) -> dict:
    """Show the current run.

    Parameters
    ----------
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with ``run_id`` key.

    Raises
    ------
    RuntimeError
        If no current run is set.
    """
    run_id = load_current_run(store_dir)
    return {"run_id": run_id, "store_dir": store_dir}


def cli_current(args) -> int:
    """Entry point for ``optagent current`` subcommand."""
    result = run_current_command(store_dir=args.store_dir)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["run_id"])
    return 0
