"""optagent CLI snapshot command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``snapshot`` subcommand parser."""
    parser = subparsers.add_parser(
        "snapshot", help="Show or rebuild the current state snapshot"
    )
    parser.add_argument("--run", default=None, help="Run identifier (optional if current run is set)")
    parser.add_argument(
        "--state-id",
        default=None,
        help="Target observed state (default: current observed state)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild snapshot from trace history (action results and derived records)",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def run_snapshot_command(
    *,
    run_id: str,
    state_id: str | None,
    rebuild: bool,
    store_dir: str,
) -> dict:
    """Show or rebuild the StateSnapshot for a run.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    state_id:
        Optional target observed state.  Defaults to current.
    rebuild:
        If ``True``, regenerate the snapshot from the state's trace
        history (artifacts, raw outputs, logs, derived records).
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with the state node dict.

    Raises
    ------
    KeyError
        If the run_id or state_id does not exist.
    """
    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    if rebuild:
        state = handle.snapshot_rebuild(state_id=state_id)
        store.save_run(handle)
    else:
        state = handle.trace_dag.nodes[handle.current_observed_state_id]
        if state_id is not None:
            state = handle.trace_dag.nodes[state_id]

    return state.to_dict()


def cli_snapshot(args) -> int:
    """Entry point for ``optagent snapshot`` subcommand.

    Prints the state snapshot as JSON to stdout.
    """
    result = run_snapshot_command(
        run_id=resolve_run_id_from_args(args),
        state_id=args.state_id,
        rebuild=args.rebuild,
        store_dir=args.store_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
