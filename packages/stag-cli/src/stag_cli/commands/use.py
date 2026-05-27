"""stag CLI use command."""

from __future__ import annotations

import argparse

from stag_cli.context import resolve_store
from stag_cli.paths import find_repo_root, resolve_store_dir, stag_id_path, write_stag_id


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``use`` subcommand parser."""
    parser = subparsers.add_parser(
        "use", help="Set the current run (writes <gitdir>/stag-id)"
    )
    parser.add_argument("run_id", help="Run identifier")
    parser.add_argument(
        "--store-dir",
        default=None,
        help="Directory where runs are stored (default: <STAG_HOME>/runs)",
    )
    return parser


def run_use_command(
    *,
    run_id: str,
    store_dir: str | None,
) -> dict:
    """Set the current run by writing its id to ``<gitdir>/stag-id``.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with ``run_id`` and ``stag_id_path`` keys.

    Raises
    ------
    KeyError
        If the run_id does not exist in the store.
    RuntimeError
        If not inside a git repository.
    """
    resolved_store_dir = store_dir if store_dir is not None else resolve_store_dir()
    store = resolve_store(resolved_store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    repo_root = find_repo_root()
    write_stag_id(repo_root, run_id)
    return {"run_id": run_id, "stag_id_path": str(stag_id_path(repo_root))}


def cli_use(args) -> int:
    """Entry point for ``stag use`` subcommand."""
    result = run_use_command(
        run_id=args.run_id,
        store_dir=args.store_dir,
    )
    print(result["run_id"])
    return 0
