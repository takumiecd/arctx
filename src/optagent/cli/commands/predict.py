"""optagent CLI predict command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``predict`` subcommand parser."""
    parser = subparsers.add_parser("predict", help="Predict outcomes for a plan")
    parser.add_argument("plan_id", help="Plan identifier")
    parser.add_argument("--run", default=None, help="Run identifier")
    parser.add_argument(
        "--predictor",
        default="default",
        help="Predictor name (default: default)",
    )
    parser.add_argument(
        "--max-outcomes",
        type=int,
        default=1,
        help="Maximum number of predicted outcomes (default: 1)",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def run_predict_command(
    *,
    run_id: str,
    plan_id: str,
    predictor: str,
    max_outcomes: int,
    store_dir: str,
) -> dict:
    """Create predicted transitions for a plan in an existing run.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    plan_id:
        Identifier of the plan to predict outcomes for.
    predictor:
        Name of the predictor to use.
    max_outcomes:
        Maximum number of predicted outcomes to create.
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with ``predictions`` key containing a list of prediction dicts.

    Raises
    ------
    KeyError
        If the run_id or plan_id does not exist.
    """
    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    predictions = handle.predict(
        plan_id=plan_id,
        predictor=predictor,
        max_outcomes=max_outcomes,
    )

    store.save_run(handle)
    return {"predictions": [p.to_dict() for p in predictions]}


def cli_predict(args) -> int:
    """Entry point for ``optagent predict`` subcommand.

    Prints the created predictions as JSON to stdout.
    """
    result = run_predict_command(
        run_id=resolve_run_id(getattr(args, 'run', None), args.store_dir),
        plan_id=args.plan_id,
        predictor=args.predictor,
        max_outcomes=args.max_outcomes,
        store_dir=args.store_dir,
    )
    print(json.dumps(result["predictions"], ensure_ascii=False, indent=2))
    return 0
