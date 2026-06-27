"""arctx git repo — manage the run's git repo registry (the repo 対応表).

One run can span several git repos. ``repo add`` is the "途中で入れる" verb:
it registers a repo into an already-running run (RepoPayload + ``.arctx-id``
pointer + ``.arctx-repo`` marker, and optionally installs hooks). ``arctx git
init`` is a thin wrapper that always installs hooks.

``repo list`` / ``repo show`` inspect the registry. These are local-inspection
commands (like ``dump``), so they show ``local_path`` by default — export is
the outlet that strips it for sharing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_lane_id_from_args,
)


# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def add_repo_parser(git_sub) -> argparse.ArgumentParser:
    p = git_sub.add_parser("repo", help="Manage the run's git repo registry (対応表)")
    sub = p.add_subparsers(dest="repo_command", required=True)

    add = sub.add_parser(
        "add", help="Register a git repo into the current run (途中で入れる)"
    )
    _add_common(add)
    add.add_argument("--repo-path", default=None, help="Repo working tree (default: cwd)")
    add.add_argument("--slug", default=None, help="Override display slug (USER/REPO)")
    add.add_argument("--no-hooks", action="store_true", help="Skip installing git hooks")
    add.add_argument("--user", default=None)
    add.add_argument("--lane", default=None)

    lst = sub.add_parser("list", help="List repos registered in the run")
    _add_common(lst)

    show = sub.add_parser("show", help="Show one repo registry entry as JSON")
    _add_common(show)
    show.add_argument("--repo-id", default=None, help="Repo id (default: resolve cwd)")
    show.add_argument("--repo-path", default=None, help="Resolve by working tree instead")

    return p


def add_init_parser(git_sub) -> argparse.ArgumentParser:
    p = git_sub.add_parser(
        "init",
        help="Set up git integration for the current run on this repo "
        "(registers the repo and installs hooks)",
    )
    _add_common(p)
    p.add_argument("--repo-path", default=None, help="Repo working tree (default: cwd)")
    p.add_argument("--slug", default=None, help="Override display slug (USER/REPO)")
    p.add_argument("--no-hooks", action="store_true", help="Skip installing git hooks")
    p.add_argument("--user", default=None)
    p.add_argument("--lane", default=None)
    return p


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--run", default=None)
    p.add_argument("--store-dir", default=None)


# ---------------------------------------------------------------------------
# add (the primitive; git init wraps it)
# ---------------------------------------------------------------------------


def run_repo_add(
    *,
    repo_path: str | None,
    slug: str | None,
    run_id: str | None,
    store_dir: str | None,
    user_id: str | None,
    lane_id: str | None,
    install_hooks: bool,
) -> dict:
    from arctx.ext.git.helpers.repo import resolve_worktree_path
    from arctx.ext.git.registry import list_repos, repo_by_id, resolve_repo_id
    from arctx.paths import find_repo_root, write_arctx_id

    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    resolved_path = resolve_worktree_path(repo_path)
    existing_ids = {r.repo_id for r in list_repos(handle.run_graph)}
    repo_id = resolve_repo_id(handle, resolved_path, slug=slug)
    entry = repo_by_id(handle.run_graph, repo_id)

    if repo_id not in existing_ids and entry is not None:
        handle.record_work_event(
            user_id=user_id,
            lane_id=lane_id,
            event_type="repo_added",
            target_kind="node",
            target_id=handle.root_node_id,
            created_records=(entry.payload_id,),
            summary=f"repo {entry.slug or repo_id} added",
            data={"repo_id": repo_id, "slug": entry.slug, "canonical": entry.canonical},
        )

    store.save_run(handle)

    # Point this repo's checkout at the run so future commands resolve it.
    try:
        repo_root = find_repo_root(resolved_path)
        write_arctx_id(repo_root, handle.run_id)
    except RuntimeError:
        repo_root = Path(resolved_path)

    hooks: dict | None = None
    if install_hooks:
        from arctx_cli.ext.git.hook import run_hook_install

        hooks = run_hook_install(repo_path=repo_root)

    result: dict = {
        "run_id": handle.run_id,
        "repo_id": repo_id,
        "slug": entry.slug if entry else None,
        "canonical": entry.canonical if entry else None,
        "local_path": entry.local_path if entry else None,
    }
    if hooks is not None:
        result["hooks"] = hooks.get("status")
    return result


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def cli_repo(args) -> int:
    if args.repo_command == "add":
        return _cli_repo_add(args)
    if args.repo_command == "list":
        return _cli_repo_list(args)
    if args.repo_command == "show":
        return _cli_repo_show(args)
    print(f"unknown repo subcommand: {args.repo_command}", file=sys.stderr)
    return 1


def cli_git_init(args) -> int:
    try:
        result = run_repo_add(
            repo_path=args.repo_path,
            slug=args.slug,
            run_id=resolve_run_id_from_args(args),
            store_dir=args.store_dir,
            user_id=resolve_user_id_from_args(args),
            lane_id=resolve_lane_id_from_args(args),
            install_hooks=not args.no_hooks,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cli_repo_add(args) -> int:
    try:
        result = run_repo_add(
            repo_path=args.repo_path,
            slug=args.slug,
            run_id=resolve_run_id_from_args(args),
            store_dir=args.store_dir,
            user_id=resolve_user_id_from_args(args),
            lane_id=resolve_lane_id_from_args(args),
            install_hooks=not args.no_hooks,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cli_repo_list(args) -> int:
    from arctx.ext.git.registry import list_repos

    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    handle = store.load_run(run_id)
    entries = [r.to_dict() for r in list_repos(handle.run_graph)]
    print(json.dumps(entries, indent=2))
    return 0


def _cli_repo_show(args) -> int:
    from arctx.ext.git.helpers.repo import resolve_worktree_path
    from arctx.ext.git.registry import read_repo_marker, repo_by_id

    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    handle = store.load_run(run_id)

    repo_id = args.repo_id
    if repo_id is None:
        marker = read_repo_marker(resolve_worktree_path(args.repo_path))
        if marker is None:
            print(
                "error: no --repo-id given and no .arctx-repo marker found in cwd",
                file=sys.stderr,
            )
            return 1
        repo_id = marker

    entry = repo_by_id(handle.run_graph, repo_id)
    if entry is None:
        print(f"error: repo not found in run: {repo_id}", file=sys.stderr)
        return 1
    print(json.dumps(entry.to_dict(), indent=2))
    return 0
