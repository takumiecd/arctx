"""optagent CLI promote command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args, resolve_user_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register promotion subcommand parsers."""
    legacy = subparsers.add_parser("promote", help="Deprecated alias for promote-transition")
    _add_promote_transition_args(legacy)

    transition = subparsers.add_parser(
        "promote-transition", help="Promote a predicted transition to an observed transition"
    )
    _add_promote_transition_args(transition)

    plan = subparsers.add_parser(
        "promote-plan", help="Promote a prediction plan to an execution plan"
    )
    plan.add_argument("--run", default=None, help="Run identifier (optional if current run is set)")
    plan.add_argument(
        "--prediction-plan",
        dest="prediction_plan_id",
        required=True,
        help="Prediction plan to promote",
    )
    plan.add_argument(
        "--to-observed-state",
        required=True,
        help="Observed state to ground the execution plan in",
    )
    plan.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    plan.add_argument("--user", default=None, help="User attribution id")
    return transition


def _add_promote_transition_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run", default=None, help="Run identifier (optional if current run is set)"
    )
    parser.add_argument(
        "--predicted-transition",
        "--predicted-transition-id",
        dest="predicted_transition_id",
        required=True,
        help="Predicted transition to match",
    )
    parser.add_argument("--result-id", required=True, help="Result identifier")
    parser.add_argument(
        "--status",
        default="completed",
        help="Execution status (default: completed)",
    )
    parser.add_argument(
        "--execution-plan",
        "--execution-plan-id",
        dest="execution_plan_id",
        required=True,
        help="Execution plan id",
    )
    parser.add_argument(
        "--metric",
        action="append",
        help="Metric as key=value (can be given multiple times)",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    parser.add_argument("--user", default=None, help="User attribution id")


def _parse_metrics(metric_list: list[str] | None) -> dict[str, float]:
    """Parse --metric key=value strings into a dict of floats."""
    metrics: dict[str, float] = {}
    if metric_list is None:
        return metrics
    for item in metric_list:
        if "=" not in item:
            raise ValueError(f"--metric must be key=value format: {item}")
        key, value = item.split("=", 1)
        try:
            metrics[key] = float(value)
        except ValueError:
            raise ValueError(f"--metric value must be numeric: {item}")
    return metrics


def run_promote_command(
    *,
    run_id: str,
    predicted_transition_id: str,
    result_id: str,
    status: str,
    execution_plan_id: str | None,
    metrics: dict[str, float] | None,
    store_dir: str,
    user_id: str | None = None,
) -> dict:
    """Promote a predicted transition into an observed transition.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    predicted_transition_id:
        Predicted transition to match against.
    result_id:
        Identifier for the result record.
    status:
        Execution status string.
    execution_plan_id:
        Explicit execution plan id.
    metrics:
        Dict of numeric metrics.
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with ``transition`` key containing the observed transition dict.

    Raises
    ------
    KeyError
        If the run_id or predicted_transition_id does not exist.
    """
    from optagent.core.schema.results import ActionResult

    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    action_result = ActionResult(
        result_id=result_id,
        execution_plan_id=execution_plan_id or "",
        status=status,
        metrics=dict(metrics or {}),
    )

    transition = handle.promote(
        mode="transition",
        predicted_transition_id=predicted_transition_id,
        action_result=action_result,
        execution_plan_id=execution_plan_id,
        user_id=user_id,
    )

    store.save_run(handle)
    return {"transition": transition.to_dict()}


def run_promote_plan_command(
    *,
    run_id: str,
    prediction_plan_id: str,
    to_observed_state_id: str,
    store_dir: str,
    user_id: str | None = None,
) -> dict:
    """Promote a PredictionPlan into an ExecutionPlan."""
    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    plans = handle.promote(
        mode="plan",
        prediction_plan_id=prediction_plan_id,
        to_observed_state_id=to_observed_state_id,
        user_id=user_id,
    )

    store.save_run(handle)
    return {"plans": [plan.to_dict() for plan in plans]}


def cli_promote_transition(args) -> int:
    """Entry point for ``optagent promote-transition`` subcommand.

    Prints the created observed transition as JSON to stdout.
    """
    result = run_promote_command(
        run_id=resolve_run_id_from_args(args),
        predicted_transition_id=args.predicted_transition_id,
        result_id=args.result_id,
        status=args.status,
        execution_plan_id=args.execution_plan_id,
        metrics=_parse_metrics(getattr(args, "metric", None)),
        store_dir=args.store_dir,
        user_id=resolve_user_id_from_args(args),
    )
    print(json.dumps(result["transition"], ensure_ascii=False, indent=2))
    return 0


def cli_promote_plan(args) -> int:
    """Entry point for ``optagent promote-plan`` subcommand."""
    result = run_promote_plan_command(
        run_id=resolve_run_id_from_args(args),
        prediction_plan_id=args.prediction_plan_id,
        to_observed_state_id=args.to_observed_state,
        store_dir=args.store_dir,
        user_id=resolve_user_id_from_args(args),
    )
    print(json.dumps(result["plans"], ensure_ascii=False, indent=2))
    return 0


cli_promote = cli_promote_transition
