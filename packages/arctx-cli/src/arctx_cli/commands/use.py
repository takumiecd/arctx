"""arctx CLI use command."""

from __future__ import annotations

import argparse

from arctx_cli.context import resolve_store
from arctx_cli.paths import find_repo_root, resolve_store_dir, arctx_id_path, write_arctx_id


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``use`` subcommand parser."""
    parser = subparsers.add_parser(
        "use", help="Set the current run (writes <gitdir>/arctx-id)"
    )
    parser.add_argument("run_id", help="Run identifier")
    parser.add_argument(
        "--store-dir",
        default=None,
        help="Directory where runs are stored (default: <ARCTX_HOME>/runs)",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help=(
            "Print 'export ARCTX_RUN_ID=<run>' for this terminal instead of "
            "writing the repo's persistent pointer. Use as: "
            'eval "$(arctx use <run> --shell)"'
        ),
    )
    return parser


def run_use_command(
    *,
    run_id: str,
    store_dir: str | None,
    shell: bool = False,
) -> dict:
    """Set the current run.

    By default this writes the run id to ``<gitdir>/arctx-id`` — a persistent,
    repo-scoped default that every terminal in that checkout sees. With
    *shell* set, nothing is written; the caller is expected to ``eval`` the
    emitted ``export ARCTX_RUN_ID=<run>`` line to pin the run for the current
    terminal only (env beats the repo pointer in the resolution chain).

    Parameters
    ----------
    run_id:
        Identifier of the run.
    store_dir:
        Directory where runs are stored.
    shell:
        Emit a shell ``export`` line (terminal-scoped) instead of writing the
        repo pointer.

    Returns
    -------
    dict with ``run_id``; ``arctx_id_path`` (repo mode) or ``export`` (shell
    mode).

    Raises
    ------
    KeyError
        If the run_id does not exist in the store.
    RuntimeError
        If not inside a git repository (repo mode only).
    """
    resolved_store_dir = store_dir if store_dir is not None else resolve_store_dir()
    store = resolve_store(resolved_store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    if shell:
        return {"run_id": run_id, "export": f"export ARCTX_RUN_ID={run_id}"}
    repo_root = find_repo_root()
    write_arctx_id(repo_root, run_id)
    return {"run_id": run_id, "arctx_id_path": str(arctx_id_path(repo_root))}


def cli_use(args) -> int:
    """Entry point for ``arctx use`` subcommand."""
    result = run_use_command(
        run_id=args.run_id,
        store_dir=args.store_dir,
        shell=getattr(args, "shell", False),
    )
    if "export" in result:
        print(result["export"])
    else:
        print(result["run_id"])
    return 0
