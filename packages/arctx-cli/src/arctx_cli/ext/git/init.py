"""arctx git init — set up git integration for the current run on this repo.

There is no repo registry: a run lives inside exactly one repository and every
git record implicitly refers to it ("absent = self"). ``git init`` therefore
only points the checkout at the run (``.arctx-id``) and installs the git hooks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from arctx_cli.context import resolve_run_id_from_args, resolve_store


def add_init_parser(git_sub) -> argparse.ArgumentParser:
    p = git_sub.add_parser(
        "init",
        help="Set up git integration for the current run on this repo "
        "(points the checkout at the run and installs hooks)",
    )
    p.add_argument("--run", default=None)
    p.add_argument("--store-dir", default=None)
    p.add_argument("--repo-path", default=None, help="Repo working tree (default: cwd)")
    p.add_argument("--no-hooks", action="store_true", help="Skip installing git hooks")
    p.add_argument("--user", default=None)
    p.add_argument("--lane", default=None)
    return p


def run_git_init(
    *,
    repo_path: str | None,
    run_id: str | None,
    store_dir: str | None,
    install_hooks: bool,
) -> dict:
    from arctx.ext.git.helpers.repo import resolve_worktree_path
    from arctx.paths import find_repo_root, write_arctx_id

    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    resolved_path = resolve_worktree_path(repo_path)
    try:
        repo_root = find_repo_root(resolved_path)
        write_arctx_id(repo_root, handle.run_id)
    except RuntimeError:
        repo_root = Path(resolved_path)

    hooks: dict | None = None
    if install_hooks:
        from arctx_cli.ext.git.hook import run_hook_install

        hooks = run_hook_install(repo_path=repo_root)

    result: dict = {"run_id": handle.run_id, "repo_path": str(repo_root)}
    if hooks is not None:
        result["hooks"] = hooks.get("status")
    return result


def cli_git_init(args) -> int:
    try:
        result = run_git_init(
            repo_path=args.repo_path,
            run_id=resolve_run_id_from_args(args),
            store_dir=args.store_dir,
            install_hooks=not args.no_hooks,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0
