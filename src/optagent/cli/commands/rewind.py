"""optagent CLI rewind command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``rewind`` subcommand parser."""
    parser = subparsers.add_parser(
        "rewind",
        help="Move the current observed state back to an ancestor (does not delete history)",
    )
    parser.add_argument("--run", default=None, help="Run identifier (optional if current run is set)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--to-state",
        dest="to_state",
        default=None,
        help="Target observed state ID (must be an ancestor of the current state)",
    )
    target.add_argument(
        "--steps",
        type=int,
        default=None,
        help="Walk this many incoming transitions from the current state",
    )
    parser.add_argument(
        "--reason",
        default=None,
        help="Optional note describing why the rewind happened",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def run_rewind_command(
    *,
    run_id: str,
    to_state: str | None,
    steps: int | None,
    reason: str | None,
    store_dir: str,
) -> dict:
    """Rewind the current observed state of *run_id* to an ancestor.

    Either *to_state* or *steps* must be given. The TraceDAG is left
    untouched; only ``current_observed_state_id`` moves and the
    PredictionDAG is re-anchored.

    Returns
    -------
    dict with the new ``state`` (post-rewind StateNode) and the new
    ``prediction_dag`` summary.

    Raises
    ------
    KeyError
        If *run_id* does not exist or *to_state* is not an observed state.
    ValueError
        If neither or both of *to_state*/*steps* are given, *steps* is
        non-positive or walks past the root, or *to_state* is not an
        ancestor of the current state.
    """
    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    state = handle.rewind(to_state_id=to_state, steps=steps, reason=reason)
    store.save_run(handle)

    return {
        "state": state.to_dict(),
        "prediction_dag": handle.prediction_dag.to_dict(),
        "reason": reason,
    }


def cli_rewind(args) -> int:
    """Entry point for ``optagent rewind`` subcommand.

    Prints the post-rewind state node as JSON to stdout.
    """
    result = run_rewind_command(
        run_id=resolve_run_id_from_args(args),
        to_state=args.to_state,
        steps=args.steps,
        reason=args.reason,
        store_dir=args.store_dir,
    )
    print(json.dumps(result["state"], ensure_ascii=False, indent=2))
    return 0
