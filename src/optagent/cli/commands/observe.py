"""optagent CLI observe command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


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


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``observe`` subcommand parser."""
    parser = subparsers.add_parser(
        "observe", help="Record an execution result without prediction match"
    )
    parser.add_argument("plan_id", help="Execution plan identifier")
    parser.add_argument("--run", default=None, help="Run identifier (optional if current run is set)")
    parser.add_argument("--result-id", required=True, help="Result identifier")
    parser.add_argument(
        "--status",
        default="completed",
        help="Execution status (default: completed)",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        help="Artifact path (can be given multiple times)",
    )
    parser.add_argument(
        "--raw-output",
        action="append",
        help="Raw output path (can be given multiple times)",
    )
    parser.add_argument(
        "--log",
        action="append",
        help="Log path (can be given multiple times)",
    )
    parser.add_argument(
        "--metric",
        action="append",
        help="Metric as key=value (can be given multiple times)",
    )
    parser.add_argument(
        "--error",
        action="append",
        help="Error message (can be given multiple times)",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def run_observe_command(
    *,
    run_id: str,
    plan_id: str,
    result_id: str,
    status: str,
    artifacts: list[str] | None,
    raw_outputs: list[str] | None,
    logs: list[str] | None,
    metrics: dict[str, float] | None,
    errors: list[str] | None,
    store_dir: str,
) -> dict:
    """Record an execution result for a plan without matching a prediction.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    plan_id:
        Identifier of the execution plan.
    result_id:
        Identifier for the result record.
    status:
        Execution status string.
    artifacts:
        List of artifact paths.
    raw_outputs:
        List of raw output paths.
    logs:
        List of log paths.
    metrics:
        Dict of numeric metrics.
    errors:
        List of error messages.
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with ``transition`` key containing the observed transition dict.

    Raises
    ------
    KeyError
        If the run_id or plan_id does not exist.
    """
    from optagent.core.schema.results import ActionResult

    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    action_result = ActionResult(
        result_id=result_id,
        execution_plan_id=plan_id,
        status=status,
        artifacts=tuple(artifacts or []),
        raw_outputs=tuple(raw_outputs or []),
        logs=tuple(logs or []),
        metrics=dict(metrics or {}),
        errors=tuple(errors or []),
    )

    transition = handle.observe(plan_id, action_result)

    store.save_run(handle)
    return {"transition": transition.to_dict()}


def cli_observe(args) -> int:
    """Entry point for ``optagent observe`` subcommand.

    Prints the created observed transition as JSON to stdout.
    """
    result = run_observe_command(
        run_id=resolve_run_id_from_args(args),
        plan_id=args.plan_id,
        result_id=args.result_id,
        status=args.status,
        artifacts=getattr(args, "artifact", None),
        raw_outputs=getattr(args, "raw_output", None),
        logs=getattr(args, "log", None),
        metrics=_parse_metrics(getattr(args, "metric", None)),
        errors=getattr(args, "error", None),
        store_dir=args.store_dir,
    )
    print(json.dumps(result["transition"], ensure_ascii=False, indent=2))
    return 0
