"""optagent CLI plan command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``plan`` subcommand parser."""
    parser = subparsers.add_parser("plan", help="Create plans from current state")
    parser.add_argument("run_id", nargs="?", default=None, help="Run identifier (optional if --run or current context is set)")
    parser.add_argument("--run", default=None, help="Run identifier")
    parser.add_argument(
        "--planner",
        default="default",
        help="Planner name (default: default)",
    )
    parser.add_argument(
        "--max-plans",
        type=int,
        default=1,
        help="Maximum number of plans to create (default: 1)",
    )
    parser.add_argument(
        "--action-type",
        default="analysis",
        help="Action category for the plan (default: analysis)",
    )
    parser.add_argument(
        "--intent",
        default=None,
        help="Description of what the plan does",
    )
    parser.add_argument(
        "--input",
        action="append",
        help="Plan input as key=value (can be given multiple times)",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def _parse_inputs(input_list: list[str] | None) -> dict[str, str]:
    """Parse --input key=value strings into a dict."""
    inputs: dict[str, str] = {}
    if input_list is None:
        return inputs
    for item in input_list:
        if "=" not in item:
            raise ValueError(f"--input must be key=value format: {item}")
        key, value = item.split("=", 1)
        inputs[key] = value
    return inputs


def run_plan_command(
    *,
    run_id: str,
    planner: str,
    max_plans: int,
    store_dir: str,
    action_type: str = "analysis",
    intent: str | None = None,
    inputs: dict[str, str] | None = None,
) -> dict:
    """Create plans from the current observed state of an existing run.

    Parameters
    ----------
    run_id:
        Identifier of the run to plan against.
    planner:
        Name of the planner to use.
    max_plans:
        Maximum number of plans to create.
    store_dir:
        Directory where runs are stored.
    action_type:
        Category of action for the plan.
    intent:
        Human-readable description of what the plan does.
    inputs:
        Key-value parameters for the plan.

    Returns
    -------
    dict with ``plans`` key containing a list of plan dicts.

    Raises
    ------
    KeyError
        If the run_id does not exist in the store.
    """
    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    plans = handle.plan(
        state_id=handle.current_observed_state_id,
        planner=planner,
        max_plans=max_plans,
        action_type=action_type,
        intent=intent,
        inputs=inputs,
    )

    store.save_run(handle)
    return {"plans": [plan.to_dict() for plan in plans]}


def cli_plan(args) -> int:
    """Entry point for ``optagent plan`` subcommand.

    Prints the created plans as JSON to stdout.
    """
    inputs = _parse_inputs(getattr(args, "input", None))
    result = run_plan_command(
        run_id=resolve_run_id(getattr(args, 'run', None), args.store_dir),
        planner=args.planner,
        max_plans=args.max_plans,
        store_dir=args.store_dir,
        action_type=args.action_type,
        intent=args.intent,
        inputs=inputs,
    )
    print(json.dumps(result["plans"], ensure_ascii=False, indent=2))
    return 0
