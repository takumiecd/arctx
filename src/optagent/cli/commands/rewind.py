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
        help="Cut an observed transition and move current to its source (does not delete history)",
    )
    parser.add_argument(
        "transition_id",
        help="Observed transition to cut (must be on the active path from current state)",
    )
    parser.add_argument("--run", default=None, help="Run identifier (optional if current run is set)")
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
    transition_id: str,
    reason: str | None,
    store_dir: str,
) -> dict:
    """Cut *transition_id* in *run_id* and rewind current to its source.

    The TraceDAG is left untouched; only ``current_observed_state_id``
    moves and a single ``TraceCut`` is appended.

    Returns
    -------
    dict with the new ``state`` (post-rewind StateNode), the new
    ``prediction_dag`` summary, and the ``cut`` record that was appended.

    Raises
    ------
    KeyError
        If *run_id* does not exist or *transition_id* is not an observed
        transition.
    ValueError
        If *transition_id* is not on the active path from current, or
        has already been cut.
    """
    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    state = handle.rewind(transition_id, reason=reason)
    cut = handle.trace_dag.cuts[handle.trace_dag.cut_order[-1]]
    store.save_run(handle)

    return {
        "state": state.to_dict(),
        "prediction_dag": handle.prediction_dag.to_dict(),
        "cut": cut.to_dict(),
    }


def cli_rewind(args) -> int:
    """Entry point for ``optagent rewind`` subcommand.

    Prints the post-rewind state node as JSON to stdout.
    """
    result = run_rewind_command(
        run_id=resolve_run_id_from_args(args),
        transition_id=args.transition_id,
        reason=args.reason,
        store_dir=args.store_dir,
    )
    print(json.dumps(result["state"], ensure_ascii=False, indent=2))
    return 0
