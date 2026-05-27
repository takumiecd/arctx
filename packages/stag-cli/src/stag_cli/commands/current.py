"""stag CLI current command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stag_cli.paths import find_repo_root, read_stag_id, resolve_stag_home


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``current`` subcommand parser."""
    parser = subparsers.add_parser("current", help="Show the current run (from <gitdir>/stag-id)")
    parser.add_argument(
        "--store-dir",
        default=None,
        help="Directory where runs are stored (default: <STAG_HOME>/runs)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    return parser


def run_current_command(
    *,
    store_dir: str | None = None,
) -> dict:
    """Show the current run resolved from ``<gitdir>/stag-id``.

    Parameters
    ----------
    store_dir:
        Ignored (kept for API compatibility). The run path is derived from
        STAG_HOME and the run_id in ``<gitdir>/stag-id``.

    Returns
    -------
    dict with ``run_id`` and ``run_path`` keys.

    Raises
    ------
    RuntimeError
        If not in a git repo or no ``<gitdir>/stag-id`` is present.
    """
    repo_root = find_repo_root()
    run_id = read_stag_id(repo_root)
    if not run_id:
        raise RuntimeError(
            "no current run set. "
            "Run 'stag init' to create a run or 'stag use <run_id>' to set one."
        )
    stag_home = resolve_stag_home()
    run_path = str(stag_home / "runs" / run_id)
    return {"run_id": run_id, "run_path": run_path}


def cli_current(args) -> int:
    """Entry point for ``stag current`` subcommand."""
    result = run_current_command(store_dir=getattr(args, "store_dir", None))
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["run_id"])
    return 0
