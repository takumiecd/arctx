"""arctx CLI ``lane`` command.

A **lane** is a solo-or-collaborative, append-only unit of work (the canonical
name for what storage still calls a work-session). It is NOT owned by one user:
any actor may append to a shared lane, and per-action attribution lives on each
event. This command is the user-facing surface for opening / listing / pinning
lanes; it reuses the work-session machinery underneath.
"""

from __future__ import annotations

import argparse
import json
import sys

from arctx_cli.commands.work_session import (
    _env_exports,
    run_work_session_start_command,
)
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``lane`` command and its sub-verbs."""
    parser = subparsers.add_parser(
        "lane",
        help="Open, list, and pin lanes (solo or collaborative units of work)",
        description=(
            "A lane is an append-only unit of work with OPEN membership: solo or "
            "shared. `lane open` creates one (optionally named); `lane env` prints "
            "shell exports to pin it for a shell/subprocess."
        ),
    )
    sub = parser.add_subparsers(dest="lane_command", required=True)

    op = sub.add_parser("open", help="Open a lane and print its id")
    op.add_argument("--run", default=None)
    op.add_argument("--lane", default=None, help="Lane id (default: a fresh id)")
    op.add_argument("--name", default=None, help="Human label for the lane")
    op.add_argument("--user", default=None, help="Actor opening the lane (created_by)")
    op.add_argument("--store-dir", default=None)
    op.add_argument("--json", action="store_true", dest="as_json")

    env = sub.add_parser("env", help="Print shell exports to pin a lane")
    env.add_argument("lane_id", nargs="?")
    env.add_argument("--run", default=None)
    env.add_argument("--new", action="store_true", dest="create_new")
    env.add_argument("--name", default=None, help="Name for the lane when --new")
    env.add_argument("--user", default=None)
    env.add_argument("--store-dir", default=None)
    env.add_argument("--json", action="store_true", dest="as_json")

    ls = sub.add_parser("list", help="List lanes in a run")
    ls.add_argument("--run", default=None)
    ls.add_argument("--store-dir", default=None)

    show = sub.add_parser("show", help="Show one lane")
    show.add_argument("lane_id")
    show.add_argument("--run", default=None)
    show.add_argument("--store-dir", default=None)

    return parser


def _lane_view(session: dict) -> dict:
    """Present a stored work-session dict under lane vocabulary."""
    return {
        "lane_id": session.get("work_session_id"),
        "name": session.get("name"),
        "created_by": session.get("user_id"),
        "parent_lane_id": session.get("parent_work_session_id"),
        "status": session.get("status"),
        "started_at": session.get("started_at"),
        "metadata": session.get("metadata", {}),
    }


def _list_lanes(*, run_id: str, store_dir: str) -> list[dict]:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    sessions = sorted(
        handle.run_graph.work_sessions.values(),
        key=lambda s: (s.started_at or "", s.work_session_id),
    )
    return [_lane_view(s.to_dict()) for s in sessions]


def cli_lane(args) -> int:
    """Dispatch the ``lane`` sub-verbs (open / env / list / show)."""
    try:
        if args.lane_command == "open":
            result = run_work_session_start_command(
                run_id=resolve_run_id_from_args(args),
                work_session_id=args.lane,
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
                name=args.name,
            )
            view = {"run_id": result["run_id"], "lane_id": result["work_session_id"],
                    "created_by": result["user_id"]}
            if args.as_json:
                print(json.dumps(view, ensure_ascii=False, indent=2))
            else:
                print(view["lane_id"])
            return 0

        if args.lane_command == "env":
            if args.create_new:
                result = run_work_session_start_command(
                    run_id=resolve_run_id_from_args(args),
                    work_session_id=args.lane_id,
                    user_id=resolve_user_id_from_args(args),
                    store_dir=args.store_dir,
                    name=args.name,
                )
            else:
                if not args.lane_id:
                    raise ValueError("lane_id is required unless --new is used")
                result = {
                    "run_id": resolve_run_id_from_args(args),
                    "work_session_id": args.lane_id,
                    "user_id": resolve_user_id_from_args(args),
                }
            if args.as_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(_env_exports(result))
            return 0

        if args.lane_command == "list":
            lanes = _list_lanes(
                run_id=resolve_run_id_from_args(args), store_dir=args.store_dir
            )
            print(json.dumps({"run_id": resolve_run_id_from_args(args),
                              "lanes": lanes}, ensure_ascii=False, indent=2))
            return 0

        if args.lane_command == "show":
            lanes = _list_lanes(
                run_id=resolve_run_id_from_args(args), store_dir=args.store_dir
            )
            for lane in lanes:
                if lane["lane_id"] == args.lane_id:
                    print(json.dumps({"lane": lane}, ensure_ascii=False, indent=2))
                    return 0
            raise KeyError(f"unknown lane_id: {args.lane_id}")
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1
