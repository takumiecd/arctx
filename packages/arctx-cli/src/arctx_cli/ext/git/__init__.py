"""arctx git subcommand — record commit hashes on steps and read them back.

This namespace does not run git. The verbs that did (``commit``, ``revert``,
``merge``, ``cherry-pick``, ``reset``, ``branch``) and the hooks that adopted
bare git operations were removed: arctx's own git subprocesses tripped arctx's
own hooks and double-recorded, and hook-driven adoption had to guess a graph
position that ``arctx add`` already tracks. What is left records what the user
states (``add``) and reads it back (``list``, ``show``, ``verify``).
"""

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

    from arctx_cli.ext.git.verify import add_parser as add_verify_parser

    add_verify_parser(git_sub)

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
    from arctx_cli.ext.git.verify import cli_verify

    if args.git_command == "add":
        return _cli_git_attach(args)
    if args.git_command == "list":
        return _cli_git_list(args)
    if args.git_command == "show":
        return _cli_git_show(args)
    if args.git_command == "verify":
        return cli_verify(args)
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
        commits.extend(getattr(payload, "commit_shas", ()))
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
    """Print each git_change record plus what git says about it right now.

    The record holds hashes and a branch; the subject/diff view under
    ``derived`` is read from the repository at this moment. When the commit is
    not in this clone, ``derived.note`` carries the explicit marker instead.
    """
    from arctx.ext.git.derive import derive_git_change  # noqa: PLC0415

    try:
        _, payloads = _git_payloads_for_step(args)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    rendered = []
    for payload in payloads:
        item = payload.to_dict()
        item["derived"] = derive_git_change(payload).to_dict()
        rendered.append(item)
    print(json.dumps(rendered, ensure_ascii=False, indent=2))
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
        force = getattr(args, "force", False)
        ensure_lane_open(handle, lane_id, force=force)
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
        force=force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
