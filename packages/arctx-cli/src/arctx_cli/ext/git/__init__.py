"""arctx git subcommand — attach commit hashes to steps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_lane_id_from_args,
)
from arctx_cli.lane_gate import ensure_lane_open

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``git`` command namespace."""
    git_parser = subparsers.add_parser("git", help="Git integration commands")
    git_sub = git_parser.add_subparsers(dest="git_command", required=True)

    from arctx_cli.ext.git.branch import add_parser as add_branch_parser
    from arctx_cli.ext.git.cherry_pick import add_parser as add_cherry_pick_parser
    from arctx_cli.ext.git.commit import add_parser as add_commit_parser
    from arctx_cli.ext.git.hook import add_parser as add_hook_parser
    from arctx_cli.ext.git.merge import add_parser as add_merge_parser
    from arctx_cli.ext.git.reset import add_parser as add_reset_parser
    from arctx_cli.ext.git.repo import add_init_parser, add_repo_parser
    from arctx_cli.ext.git.revert import add_parser as add_revert_parser
    from arctx_cli.ext.git.verify import add_parser as add_verify_parser
    from arctx_cli.ext.git.worktree import add_parser as add_worktree_parser

    add_branch_parser(git_sub)
    add_cherry_pick_parser(git_sub)
    add_commit_parser(git_sub)
    add_hook_parser(git_sub)
    add_init_parser(git_sub)
    add_merge_parser(git_sub)
    add_repo_parser(git_sub)
    add_reset_parser(git_sub)
    add_revert_parser(git_sub)
    add_verify_parser(git_sub)
    add_worktree_parser(git_sub)

    sp_list = git_sub.add_parser("list", help="List git_change payloads for a Step")
    sp_list.add_argument("--step", required=True, dest="step_id")
    sp_list.add_argument("--run", default=None)
    sp_list.add_argument("--store-dir", default=None)

    sp_add = git_sub.add_parser("add", help="Attach explicit Git commits to a Step")
    sp_add.add_argument("--step", required=True, dest="step_id")
    sp_add.add_argument("--commit", action="append", required=True, dest="commits")
    sp_add.add_argument("--run", default=None)
    sp_add.add_argument("--store-dir", default=None)
    sp_add.add_argument("--user", default=None)
    sp_add.add_argument("--lane", default=None)
    sp_add.add_argument("--force", action="store_true",
                        help="Write even if the target lane is closed")

    sp_show = git_sub.add_parser("show", help="Show git_change payloads for a Step")
    sp_show.add_argument("--step", required=True, dest="step_id")
    sp_show.add_argument("--run", default=None)
    sp_show.add_argument("--store-dir", default=None)

    return git_parser

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_dir(store: object, run_id: str) -> Path:
    return store.run_path(run_id)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def cli_git(args) -> int:
    """Dispatch canonical ``arctx git`` subcommands."""
    from arctx_cli.ext.git.branch import cli_branch
    from arctx_cli.ext.git.cherry_pick import cli_cherry_pick
    from arctx_cli.ext.git.commit import cli_commit
    from arctx_cli.ext.git.hook import cli_hook
    from arctx_cli.ext.git.merge import cli_merge
    from arctx_cli.ext.git.reset import cli_reset
    from arctx_cli.ext.git.revert import cli_revert
    from arctx_cli.ext.git.verify import cli_verify

    if args.git_command == "add":
        return _cli_git_attach(args)
    if args.git_command == "branch":
        return cli_branch(args)
    if args.git_command == "cherry-pick":
        return cli_cherry_pick(args)
    if args.git_command == "commit":
        return cli_commit(args)
    if args.git_command == "hook":
        return cli_hook(args)
    if args.git_command == "init":
        from arctx_cli.ext.git.repo import cli_git_init  # noqa: PLC0415

        return cli_git_init(args)
    if args.git_command == "list":
        return _cli_git_list(args)
    if args.git_command == "merge":
        return cli_merge(args)
    if args.git_command == "repo":
        from arctx_cli.ext.git.repo import cli_repo  # noqa: PLC0415

        return cli_repo(args)
    if args.git_command == "reset":
        return cli_reset(args)
    if args.git_command == "revert":
        return cli_revert(args)
    if args.git_command == "show":
        return _cli_git_show(args)
    if args.git_command == "verify":
        return cli_verify(args)
    if args.git_command == "worktree":
        from arctx_cli.ext.git.worktree import cli_worktree  # noqa: PLC0415

        return cli_worktree(args)
    print(f"unknown git subcommand: {args.git_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# attach
# ---------------------------------------------------------------------------


def _git_payloads_for_step(args) -> tuple[object, list]:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    if args.step_id not in handle.run_graph.steps:
        raise KeyError(f"unknown step_id: {args.step_id}")
    payloads = handle.run_graph.payloads_for_step(
        args.step_id,
        payload_type="git_change",
    )
    return handle, payloads


def _cli_git_list(args) -> int:
    try:
        _, payloads = _git_payloads_for_step(args)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    commits: list[str] = []
    for payload in payloads:
        for entry in getattr(payload, "commit_log", ()):
            sha = getattr(entry, "sha", None)
            if sha is not None:
                commits.append(str(sha))
    print(
        json.dumps(
            {
                "step_id": args.step_id,
                "commits": commits,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cli_git_show(args) -> int:
    try:
        _, payloads = _git_payloads_for_step(args)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps([p.to_dict() for p in payloads], ensure_ascii=False, indent=2))
    return 0


def _cli_git_attach(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    lane_id = resolve_lane_id_from_args(args)

    if not store.run_path(run_id).exists():
        print(f"error: unknown run_id: {run_id}", file=sys.stderr)
        return 1

    handle = store.load_run(run_id)
    run_dir = _run_dir(store, run_id)

    from arctx.ext.git.helpers.attach import attach_commits_to_step

    try:
        ensure_lane_open(handle, lane_id, force=getattr(args, "force", False))
        before = graph_counts(handle)
        result = attach_commits_to_step(
            handle,
            run_dir,
            args.step_id,
            tuple(args.commits),
            user_id=user_id,
            lane_id=lane_id,
        )
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane_id,
        before=before,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
