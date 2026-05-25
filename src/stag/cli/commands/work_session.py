"""stag CLI work-session command."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from os import environ

from stag.cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
)
from stag.core.append import AppendBatch
from stag.core.ids import opaque_id


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "work-session",
        help="Create and use fixed work sessions",
    )
    work_sub = parser.add_subparsers(dest="work_session_command", required=True)

    start = work_sub.add_parser("start", help="Create a work session")
    start.add_argument("--run", default=None)
    start.add_argument("--work-session", default=None)
    start.add_argument("--user", default=None)
    start.add_argument("--store-dir", default=".stag/runs")
    start.add_argument("--json", action="store_true", dest="as_json")

    env = work_sub.add_parser("env", help="Print shell exports for a fixed work session")
    env.add_argument("work_session_id", nargs="?")
    env.add_argument("--run", default=None)
    env.add_argument("--new", action="store_true", dest="create_new")
    env.add_argument("--user", default=None)
    env.add_argument("--store-dir", default=".stag/runs")
    env.add_argument("--json", action="store_true", dest="as_json")

    spawn = work_sub.add_parser("spawn", help="Run a command with a fixed work session")
    spawn.add_argument("--run", default=None)
    spawn.add_argument("--work-session", default=None)
    spawn.add_argument("--user", default=None)
    spawn.add_argument("--store-dir", default=".stag/runs")
    spawn.add_argument("command", nargs=argparse.REMAINDER)

    list_cmd = work_sub.add_parser("list", help="List work sessions in a run")
    list_cmd.add_argument("--run", default=None)
    list_cmd.add_argument("--store-dir", default=".stag/runs")

    show = work_sub.add_parser("show", help="Show one work session")
    show.add_argument("work_session_id")
    show.add_argument("--run", default=None)
    show.add_argument("--store-dir", default=".stag/runs")

    return parser


def run_work_session_start_command(
    *,
    run_id: str,
    work_session_id: str | None,
    user_id: str,
    store_dir: str,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    ws_id = work_session_id or opaque_id("ws")
    session = handle.ensure_work_session(user_id=user_id, work_session_id=ws_id)
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
    return {"run_id": run_id, "work_session_id": ws_id, "user_id": user_id}


def run_work_session_env_command(
    *,
    run_id: str,
    work_session_id: str | None,
    create_new: bool,
    user_id: str,
    store_dir: str,
) -> dict:
    if create_new:
        return run_work_session_start_command(
            run_id=run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            store_dir=store_dir,
        )
    if not work_session_id:
        raise ValueError("work_session_id is required unless --new is used")
    return {"run_id": run_id, "work_session_id": work_session_id, "user_id": user_id}


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
            )
            child_env = dict(environ)
            child_env["STAG_RUN_ID"] = result["run_id"]
            child_env["STAG_WORK_SESSION_ID"] = result["work_session_id"]
            child_env["STAG_USER_ID"] = result["user_id"]
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
    return "\n".join(
        [
            f"export STAG_RUN_ID={shlex.quote(result['run_id'])}",
            f"export STAG_WORK_SESSION_ID={shlex.quote(result['work_session_id'])}",
            f"export STAG_USER_ID={shlex.quote(result['user_id'])}",
        ]
    )
