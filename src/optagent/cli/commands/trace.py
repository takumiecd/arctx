"""optagent CLI trace command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``trace`` subcommand parser."""
    parser = subparsers.add_parser("trace", help="Trace observed history from current state")
    parser.add_argument("--run", default=None, help="Run identifier (optional if current run is set)")
    parser.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Maximum number of transitions to trace back",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def run_trace_command(
    *,
    run_id: str,
    depth: int | None,
    store_dir: str,
) -> dict:
    """Trace observed history backwards from the current state.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    depth:
        Maximum number of transitions to include.
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with ``history`` key containing the TraceContext dict.

    Raises
    ------
    KeyError
        If the run_id does not exist.
    """
    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    history = handle.trace(depth=depth)
    return {"history": history.to_dict()}


def cli_trace(args) -> int:
    """Entry point for ``optagent trace`` subcommand.

    Prints the trace history as JSON to stdout.
    """
    result = run_trace_command(
        run_id=resolve_run_id_from_args(args),
        depth=args.depth,
        store_dir=args.store_dir,
    )
    print(json.dumps(result["history"], ensure_ascii=False, indent=2))
    return 0
