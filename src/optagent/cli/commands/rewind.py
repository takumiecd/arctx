"""optagent CLI rewind command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args, resolve_user_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``rewind`` subcommand parser."""
    parser = subparsers.add_parser(
        "rewind",
        help="Cut an observed transition from an explicit validation state",
    )
    parser.add_argument(
        "--transition",
        dest="transition_id",
        required=True,
        help="Observed transition to cut",
    )
    parser.add_argument(
        "--from-state",
        required=True,
        help="Active observed state to validate backward reachability from",
    )
    parser.add_argument(
        "--run", default=None, help="Run identifier (optional if current run is set)"
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
    parser.add_argument("--user", default=None, help="User attribution id")
    return parser


def run_rewind_command(
    *,
    run_id: str,
    transition_id: str,
    from_state_id: str,
    reason: str | None,
    store_dir: str,
    user_id: str | None = None,
) -> dict:
    """Cut *transition_id* in *run_id* from an explicit validation state.

    Returns
    -------
    dict with the appended ``cut`` record. The new current observed
    state ID is available as ``cut["rewound_to_state_id"]``.

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

    cut = handle.rewind(
        transition_id,
        from_state_id=from_state_id,
        reason=reason,
        user_id=user_id,
    )
    store.save_run(handle)

    return {"cut": cut.to_dict()}


def cli_rewind(args) -> int:
    """Entry point for ``optagent rewind`` subcommand.

    Prints the appended ``TraceCut`` record as JSON to stdout.
    """
    result = run_rewind_command(
        run_id=resolve_run_id_from_args(args),
        transition_id=args.transition_id,
        from_state_id=args.from_state,
        reason=args.reason,
        store_dir=args.store_dir,
        user_id=resolve_user_id_from_args(args),
    )
    print(json.dumps(result["cut"], ensure_ascii=False, indent=2))
    return 0
