"""optagent CLI refresh command."""

from __future__ import annotations

import argparse
import json

from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``refresh`` subcommand parser."""
    parser = subparsers.add_parser(
        "refresh", help="Re-anchor the PredictionDAG to the current observed state"
    )
    parser.add_argument("run_id", help="Run identifier")
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def run_refresh_command(
    *,
    run_id: str,
    store_dir: str,
) -> dict:
    """Re-anchor the PredictionDAG for a run.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with ``prediction_dag`` key containing the new DAG dict.

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

    new_dag = handle.refresh()

    store.save_run(handle)
    return {"prediction_dag": new_dag.to_dict()}


def cli_refresh(args) -> int:
    """Entry point for ``optagent refresh`` subcommand.

    Prints the new PredictionDAG as JSON to stdout.
    """
    result = run_refresh_command(
        run_id=args.run_id,
        store_dir=args.store_dir,
    )
    print(json.dumps(result["prediction_dag"], ensure_ascii=False, indent=2))
    return 0
