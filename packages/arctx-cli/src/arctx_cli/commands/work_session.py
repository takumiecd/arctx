"""arctx CLI work-session command."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from os import environ

from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
)
from arctx.core.append import AppendBatch
from arctx.core.ids import opaque_id


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "work-session",
        help="Create, inspect, and pin work sessions for parallel work",
        description=(
            "Create and use work sessions. Use explicit mode with --work-session on "
            "mutating commands, or fixed mode via `eval \"$(arctx work-session env "
            "--run RUN --new)\"`. Fixed mode writes only shell environment variables, "
            "so parallel terminals and child processes do not share the <gitdir>/arctx-id pointer."
        ),
    )
    work_sub = parser.add_subparsers(dest="work_session_command", required=True)

    start = work_sub.add_parser(
        "start",
        help="Create a work session and print its id",
        description=(
            "Create a work session in a run. This does not switch global state; pass "
            "the id with --work-session or use `work-session env` for shell-local "
            "fixed mode."
        ),
    )
    start.add_argument("--run", default=None)
    start.add_argument("--work-session", default=None)
    start.add_argument("--user", default=None)
    start.add_argument("--store-dir", default=None)
    start.add_argument(
        "--worktree",
        default=None,
        metavar="PATH",
        help=(
            "Attach this work session to a git worktree at PATH. The path "
            "is recorded in WorkSession.metadata and exported as "
            "ARCTX_GIT_WORKTREE for child processes."
        ),
    )
    start.add_argument("--json", action="store_true", dest="as_json")

    env = work_sub.add_parser(
        "env",
        help="Print shell exports for shell-local fixed mode",
        description=(
            "Print exports for ARCTX_RUN_ID, ARCTX_WORK_SESSION_ID, and ARCTX_USER_ID. "
            "Use eval with this output to pin only the current shell or subprocess "
            "environment, which is safe for parallel terminals."
        ),
    )
    env.add_argument("work_session_id", nargs="?")
    env.add_argument("--run", default=None)
    env.add_argument("--new", action="store_true", dest="create_new")
    env.add_argument("--user", default=None)
    env.add_argument("--store-dir", default=None)
    env.add_argument(
        "--worktree",
        default=None,
        metavar="PATH",
        help=(
            "Attach the session to a git worktree at PATH. With --new the "
            "path is stored on the new WorkSession; the exports include "
            "ARCTX_GIT_WORKTREE=PATH so subsequent git verbs run there."
        ),
    )
    env.add_argument("--json", action="store_true", dest="as_json")

    spawn = work_sub.add_parser(
        "spawn",
        help="Run a command with a child-only fixed work session",
        description=(
            "Run a child command with ARCTX_RUN_ID, ARCTX_WORK_SESSION_ID, and "
            "ARCTX_USER_ID set only in that child process. Use this for Codex, "
            "Claude Code, scripts, or other parallel workers."
        ),
    )
    spawn.add_argument("--run", default=None)
    spawn.add_argument("--work-session", default=None)
    spawn.add_argument("--user", default=None)
    spawn.add_argument("--store-dir", default=None)
    spawn.add_argument(
        "--worktree",
        default=None,
        metavar="PATH",
        help=(
            "Attach the child session to a git worktree at PATH and export "
            "ARCTX_GIT_WORKTREE=PATH for the child command."
        ),
    )
    spawn.add_argument("command", nargs=argparse.REMAINDER)

    list_cmd = work_sub.add_parser("list", help="List work sessions in a run")
    list_cmd.add_argument("--run", default=None)
    list_cmd.add_argument("--store-dir", default=None)

    show = work_sub.add_parser("show", help="Show one work session")
    show.add_argument("work_session_id")
    show.add_argument("--run", default=None)
    show.add_argument("--store-dir", default=None)

    return parser


def run_work_session_start_command(
    *,
    run_id: str,
    work_session_id: str | None,
    user_id: str,
    store_dir: str,
    worktree: str | None = None,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    ws_id = work_session_id or opaque_id("ws")
    metadata = _build_worktree_metadata(worktree)
    session = handle.ensure_work_session(
        user_id=user_id,
        work_session_id=ws_id,
        metadata=metadata or None,
    )
    if session is None:
        raise RuntimeError("failed to create work session")
    if hasattr(store, "append_batch"):
        store.append_batch(
            AppendBatch(
                run_id=run_id,
                user_id=user_id,
                work_session_id=ws_id,
                work_session=session,
                records=(),
                events=(),
            )
        )
    else:
        store.save_run(handle)
    result = {"run_id": run_id, "work_session_id": ws_id, "user_id": user_id}
    if worktree:
        result["worktree"] = str(metadata["worktree"]["path"])
    return result


def _build_worktree_metadata(worktree: str | None) -> dict:
    """Resolve worktree path to absolute path and capture branch / repo info.

    Returns the metadata dict to store on the WorkSession, or an empty
    dict when no worktree was requested. The path is normalised so that
    it does not depend on the caller's cwd; the branch lookup is best
    effort and silently degrades when git is unavailable or the path is
    not a real worktree.
    """
    if not worktree:
        return {}
    from pathlib import Path  # noqa: PLC0415

    path = Path(worktree).expanduser().resolve()
    info: dict = {"path": str(path)}
    try:
        from arctx.ext.git.helpers import repo as git_repo  # noqa: PLC0415

        branch = git_repo.current_branch(path)
        if branch is not None:
            info["branch"] = branch
        info["repo_common_dir"] = str(git_repo.common_dir(path))
    except Exception:  # noqa: BLE001
        # Recording the path is still useful; git lookups are best-effort.
        pass
    return {"worktree": info}


def run_work_session_env_command(
    *,
    run_id: str,
    work_session_id: str | None,
    create_new: bool,
    user_id: str,
    store_dir: str,
    worktree: str | None = None,
) -> dict:
    if create_new:
        return run_work_session_start_command(
            run_id=run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            store_dir=store_dir,
            worktree=worktree,
        )
    if not work_session_id:
        raise ValueError("work_session_id is required unless --new is used")
    result = {"run_id": run_id, "work_session_id": work_session_id, "user_id": user_id}
    if worktree:
        from pathlib import Path  # noqa: PLC0415

        result["worktree"] = str(Path(worktree).expanduser().resolve())
    return result


def run_work_session_list_command(*, run_id: str, store_dir: str) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    return {
        "run_id": run_id,
        "work_sessions": [
            session.to_dict()
            for session in sorted(
                handle.run_graph.work_sessions.values(),
                key=lambda s: (s.started_at or "", s.work_session_id),
            )
        ],
    }


def run_work_session_show_command(
    *,
    run_id: str,
    work_session_id: str,
    store_dir: str,
) -> dict:
    listed = run_work_session_list_command(run_id=run_id, store_dir=store_dir)
    for session in listed["work_sessions"]:
        if session["work_session_id"] == work_session_id:
            return {"run_id": run_id, "work_session": session}
    raise KeyError(f"unknown work_session_id: {work_session_id}")


def cli_work_session(args) -> int:
    try:
        if args.work_session_command == "start":
            result = run_work_session_start_command(
                run_id=resolve_run_id_from_args(args),
                work_session_id=args.work_session,
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
                worktree=getattr(args, "worktree", None),
            )
            _print_result(result, as_json=args.as_json)
            return 0

        if args.work_session_command == "env":
            result = run_work_session_env_command(
                run_id=resolve_run_id_from_args(args),
                work_session_id=args.work_session_id,
                create_new=args.create_new,
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
                worktree=getattr(args, "worktree", None),
            )
            if args.as_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(_env_exports(result))
            return 0

        if args.work_session_command == "spawn":
            if not args.command:
                raise ValueError("spawn requires a command after --")
            result = run_work_session_start_command(
                run_id=resolve_run_id_from_args(args),
                work_session_id=args.work_session,
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
                worktree=getattr(args, "worktree", None),
            )
            child_env = dict(environ)
            child_env["ARCTX_RUN_ID"] = result["run_id"]
            child_env["ARCTX_WORK_SESSION_ID"] = result["work_session_id"]
            child_env["ARCTX_USER_ID"] = result["user_id"]
            if result.get("worktree"):
                child_env["ARCTX_GIT_WORKTREE"] = result["worktree"]
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            return subprocess.call(command, env=child_env)

        if args.work_session_command == "list":
            result = run_work_session_list_command(
                run_id=resolve_run_id_from_args(args),
                store_dir=args.store_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.work_session_command == "show":
            result = run_work_session_show_command(
                run_id=resolve_run_id_from_args(args),
                work_session_id=args.work_session_id,
                store_dir=args.store_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


def _print_result(result: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["work_session_id"])


def _env_exports(result: dict) -> str:
    lines = [
        f"export ARCTX_RUN_ID={shlex.quote(result['run_id'])}",
        f"export ARCTX_WORK_SESSION_ID={shlex.quote(result['work_session_id'])}",
        f"export ARCTX_USER_ID={shlex.quote(result['user_id'])}",
    ]
    if result.get("worktree"):
        lines.append(f"export ARCTX_GIT_WORKTREE={shlex.quote(result['worktree'])}")
    return "\n".join(lines)
