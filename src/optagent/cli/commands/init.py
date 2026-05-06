"""optagent CLI init command."""

from __future__ import annotations

import argparse
from pathlib import Path

import optagent
from optagent.cli.context import save_current_run
from optagent.core.schema.requirements import Requirement
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``init`` subcommand parser."""
    parser = subparsers.add_parser("init", help="Initialize a new run")
    parser.add_argument("requirement_id", help="Requirement identifier")
    parser.add_argument(
        "--target-type",
        default="code",
        help="Target category (default: code)",
    )
    parser.add_argument(
        "--target-id",
        default=None,
        help="Specific target identifier (default: requirement_id)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit run id (default: auto-generated)",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory to save runs (default: .optagent/runs)",
    )
    return parser


def run_init_command(
    *,
    requirement_id: str,
    target_type: str,
    target_id: str | None,
    run_id: str | None,
    store_dir: str,
) -> dict[str, str]:
    """Create a new run and save it to disk.

    Parameters
    ----------
    requirement_id:
        Identifier for the requirement.
    target_type:
        Category of the target (e.g. "code", "kernel").
    target_id:
        Specific target identifier.
    run_id:
        Explicit run id. If None, one is generated automatically.
    store_dir:
        Directory under which run directories are created.

    Returns
    -------
    dict with at least ``run_id``.

    Raises
    ------
    FileExistsError
        If the run directory already exists.
    """
    requirement = Requirement(
        requirement_id=requirement_id,
        target_type=target_type,
        target_id=target_id or requirement_id,
    )

    handle = optagent.init(requirement, run_id=run_id)

    store = JsonlRunStore(store_dir)
    run_path = store.run_path(handle.run_id)
    if run_path.exists():
        raise FileExistsError(f"run directory already exists: {run_path}")

    store.save_run(handle)
    save_current_run(handle.run_id, store_dir)
    return {"run_id": handle.run_id}


def cli_init(args) -> int:
    """Entry point for ``optagent init`` subcommand.

    Prints the generated run_id to stdout on success.
    """
    result = run_init_command(
        requirement_id=args.requirement_id,
        target_type=args.target_type,
        target_id=args.target_id,
        run_id=args.run_id,
        store_dir=args.store_dir,
    )
    print(result["run_id"])
    return 0
