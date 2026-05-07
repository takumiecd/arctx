"""optagent CLI show command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``show`` subcommand parser."""
    parser = subparsers.add_parser("show", help="Show run details")
    parser.add_argument("--run", default=None, help="Run identifier (optional if current run is set)")
    parser.add_argument(
        "--state",
        dest="state_id",
        default=None,
        help="Show a specific state by ID",
    )
    parser.add_argument(
        "--plan",
        dest="plan_id",
        default=None,
        help="Show a specific plan by ID",
    )
    parser.add_argument(
        "--transition",
        dest="transition_id",
        default=None,
        help="Show a specific transition by ID",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def run_show_command(
    *,
    run_id: str,
    state_id: str | None,
    plan_id: str | None,
    transition_id: str | None,
    store_dir: str,
) -> dict:
    """Show details for a run or a specific entity within it.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    state_id:
        Optional state ID to show.
    plan_id:
        Optional plan ID to show.
    transition_id:
        Optional transition ID to show.
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with requested details.

    Raises
    ------
    KeyError
        If the run_id or requested entity does not exist.
    """
    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    if state_id is not None:
        state = handle.trace_dag.nodes.get(state_id) or handle.prediction_dag.nodes.get(state_id)
        if state is None:
            raise KeyError(f"unknown state_id: {state_id}")
        return {"state": state.to_dict()}

    if plan_id is not None:
        plan = handle.trace_dag.execution_plans.get(plan_id) or handle.prediction_dag.plans.get(plan_id)
        if plan is None:
            raise KeyError(f"unknown plan_id: {plan_id}")
        return {"plan": plan.to_dict()}

    if transition_id is not None:
        transition = handle.trace_dag.transitions.get(transition_id) or handle.prediction_dag.transitions.get(transition_id)
        if transition is None:
            raise KeyError(f"unknown transition_id: {transition_id}")
        return {"transition": transition.to_dict()}

    return {
        "run_id": handle.run_id,
        "requirement_id": handle.requirement.requirement_id,
        "current_observed_state_id": handle.current_observed_state_id,
        "trace_dag": handle.trace_dag.to_dict(),
        "prediction_dag": handle.prediction_dag.to_dict(),
    }


def cli_show(args) -> int:
    """Entry point for ``optagent show`` subcommand.

    Prints the result as JSON to stdout.
    """
    result = run_show_command(
        run_id=resolve_run_id_from_args(args),
        state_id=args.state_id,
        plan_id=args.plan_id,
        transition_id=args.transition_id,
        store_dir=args.store_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
