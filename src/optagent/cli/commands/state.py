"""optagent CLI state command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``state`` subcommand parser."""
    parser = subparsers.add_parser("state", help="Show or update an observed state snapshot")
    parser.add_argument("--run", default=None, help="Run identifier (optional if current run is set)")
    parser.add_argument("--state-id", required=True, help="Observed state identifier")
    parser.add_argument(
        "--add-knowledge",
        action="append",
        help="Add a knowledge summary (can be given multiple times)",
    )
    parser.add_argument(
        "--add-open-question",
        action="append",
        help="Add an open question (can be given multiple times)",
    )
    parser.add_argument(
        "--add-artifact",
        action="append",
        help="Add an artifact as id:type:path (can be given multiple times)",
    )
    parser.add_argument(
        "--add-prediction",
        action="append",
        help="Add a prediction as id:summary (can be given multiple times)",
    )
    parser.add_argument(
        "--add-branch",
        action="append",
        help="Add an active branch id (can be given multiple times)",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def _parse_artifact(value: str) -> tuple[str, str, str | None]:
    parts = value.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"--add-artifact must be id:type:path or id:type: {value}")
    artifact_id = parts[0]
    artifact_type = parts[1]
    path = parts[2] if len(parts) > 2 and parts[2] else None
    return artifact_id, artifact_type, path


def _parse_prediction(value: str) -> tuple[str, str]:
    parts = value.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"--add-prediction must be id:summary: {value}")
    return parts[0], parts[1]


def run_state_command(
    *,
    run_id: str,
    store_dir: str,
    state_id: str,
    add_knowledge: list[str] | None,
    add_open_question: list[str] | None,
    add_artifact: list[str] | None,
    add_prediction: list[str] | None,
    add_branch: list[str] | None,
) -> dict:
    """Show or update an observed state snapshot for a run.

    If any ``--add-*`` option is given, the state is updated and saved.
    Otherwise the current state is returned read-only.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    store_dir:
        Directory where runs are stored.
    add_knowledge:
        Knowledge summaries to append.
    add_open_question:
        Open questions to append.
    add_artifact:
        Artifact descriptors (``id:type:path``) to append.
    add_prediction:
        Prediction descriptors (``id:summary``) to append.
    add_branch:
        Branch identifiers to append.

    Returns
    -------
    dict with ``state`` key containing the state node dict.

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

    will_update = any(
        [add_knowledge, add_open_question, add_artifact, add_prediction, add_branch]
    )

    if will_update:
        artifacts = [_parse_artifact(v) for v in add_artifact or []]
        predictions = [_parse_prediction(v) for v in add_prediction or []]
        state = handle.state_update(
            state_id=state_id,
            add_knowledge=add_knowledge,
            add_open_question=add_open_question,
            add_artifact=artifacts or None,
            add_prediction=predictions or None,
            add_branch=add_branch,
        )
        store.save_run(handle)
    else:
        state = handle.state_show(state_id)

    return {"state": state.to_dict()}


def cli_state(args) -> int:
    """Entry point for ``optagent state`` subcommand.

    Prints the state as JSON to stdout.
    """
    result = run_state_command(
        run_id=resolve_run_id_from_args(args),
        store_dir=args.store_dir,
        state_id=args.state_id,
        add_knowledge=getattr(args, "add_knowledge", None),
        add_open_question=getattr(args, "add_open_question", None),
        add_artifact=getattr(args, "add_artifact", None),
        add_prediction=getattr(args, "add_prediction", None),
        add_branch=getattr(args, "add_branch", None),
    )
    print(json.dumps(result["state"], ensure_ascii=False, indent=2))
    return 0
