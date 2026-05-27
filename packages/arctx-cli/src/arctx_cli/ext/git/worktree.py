"""arctx git worktree — thin wrappers around ``git worktree``.

This is a lifecycle helper. The actual graph state lives on the
WorkSession that is later attached to the worktree via
``arctx work-session env --worktree`` (or via spawn/start). These
commands only manage the git side: ``add`` creates a new
``git worktree`` on a fresh branch, ``list`` shows the registered
worktrees, and ``remove`` invokes ``git worktree remove``.

Recording per-worktree session metadata is intentionally left to
``arctx work-session start --worktree``; that keeps a single canonical
path for writing WorkSession state and lets users attach a worktree
that was created outside arctx (``git worktree add`` directly).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from arctx.ext.git.helpers.repo import resolve_worktree_path


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``worktree`` subcommand under ``arctx git``."""
    parser = subparsers.add_parser(
        "worktree",
        help="Manage git worktrees attached to this ARCTX run",
        description=(
            "Thin wrapper around `git worktree`. Use these to create / list "
            "/ remove worktrees; attach them to a ARCTX work session with "
            "`arctx work-session start --worktree PATH`."
        ),
    )
    sub = parser.add_subparsers(dest="worktree_command", required=True)

    add = sub.add_parser(
        "add",
        help="git worktree add PATH [BRANCH] — create a new worktree",
    )
    add.add_argument("path", help="Filesystem path for the new worktree")
    add.add_argument(
        "branch",
        nargs="?",
        default=None,
        help="Branch to check out. Defaults to a new branch named after the path leaf.",
    )
    add.add_argument(
        "--base",
        default=None,
        help="Base ref for the new branch (defaults to HEAD).",
    )
    add.add_argument(
        "--existing-branch",
        action="store_true",
        help="Check out an existing branch instead of creating one.",
    )
    add.add_argument("--store-dir", default=None)

    list_cmd = sub.add_parser("list", help="git worktree list --porcelain (parsed as JSON)")
    list_cmd.add_argument("--store-dir", default=None)

    remove = sub.add_parser("remove", help="git worktree remove PATH")
    remove.add_argument("path")
    remove.add_argument(
        "--force",
        action="store_true",
        help="Pass --force to git worktree remove (drop dirty / locked).",
    )
    remove.add_argument("--store-dir", default=None)

    return parser


def cli_worktree(args) -> int:
    """Dispatch ``arctx git worktree`` subcommands."""
    if args.worktree_command == "add":
        return _cli_worktree_add(args)
    if args.worktree_command == "list":
        return _cli_worktree_list(args)
    if args.worktree_command == "remove":
        return _cli_worktree_remove(args)
    print(f"unknown worktree subcommand: {args.worktree_command}", file=sys.stderr)
    return 1


def _cli_worktree_add(args) -> int:
    target = Path(args.path).expanduser().resolve()
    cwd = resolve_worktree_path(None)
    cmd = ["git", "worktree", "add"]
    if args.branch is None and not args.existing_branch:
        leaf = target.name or "arctx-worktree"
        cmd += ["-b", leaf, str(target)]
        if args.base:
            cmd.append(args.base)
    elif args.existing_branch:
        if args.branch is None:
            print("error: --existing-branch requires BRANCH", file=sys.stderr)
            return 2
        cmd += [str(target), args.branch]
    else:
        # explicit new branch name
        cmd += ["-b", args.branch, str(target)]
        if args.base:
            cmd.append(args.base)

    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode

    print(
        json.dumps(
            {
                "path": str(target),
                "branch": args.branch
                or (target.name or "arctx-worktree" if not args.existing_branch else None),
                "command": cmd,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cli_worktree_list(args) -> int:  # noqa: ARG001
    cwd = resolve_worktree_path(None)
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode

    entries: list[dict] = []
    current: dict = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        if " " in line:
            key, value = line.split(" ", 1)
        else:
            key, value = line, ""
        current[key] = value
    if current:
        entries.append(current)

    print(json.dumps({"worktrees": entries}, ensure_ascii=False, indent=2))
    return 0


def _cli_worktree_remove(args) -> int:
    cwd = resolve_worktree_path(None)
    cmd = ["git", "worktree", "remove"]
    if args.force:
        cmd.append("--force")
    cmd.append(str(Path(args.path).expanduser()))
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    print(json.dumps({"removed": str(Path(args.path).expanduser().resolve())}, indent=2))
    return 0
