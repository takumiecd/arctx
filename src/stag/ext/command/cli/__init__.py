"""CLI commands for the command extension."""

from __future__ import annotations

import argparse
import json
import sys

from stag.cli.append_batch import graph_counts, maybe_append_or_save
from stag.cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("command", help="Run external commands")
    command_sub = parser.add_subparsers(dest="command_command", required=True)

    sp_run = command_sub.add_parser(
        "run",
        help="Run an external command and record its result",
    )
    sp_run.add_argument("--run", default=None)
    sp_run.add_argument("--store-dir", default=None)
    sp_run.add_argument("--user", default=None)
    sp_run.add_argument("--work-session", default=None)
    sp_run.add_argument("--cwd", default=None)
    sp_run.add_argument("--max-output-chars", type=int, default=20000)
    sp_run.add_argument(
        "argv",
        nargs=argparse.REMAINDER,
        help="Command to execute. Prefix with -- when needed.",
    )
    return parser


def run_command_run_command(
    *,
    run_id: str,
    store_dir: str,
    argv: list[str],
    cwd: str | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
    max_output_chars: int = 20000,
) -> dict[str, object]:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    if not hasattr(handle, "command"):
        raise RuntimeError("command extension is not enabled for this run")

    before = graph_counts(handle)
    result = handle.command.run(
        command=argv,
        cwd=cwd,
        user_id=user_id,
        work_session_id=work_session_id,
        max_output_chars=max_output_chars,
    )
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=work_session_id,
        before=before,
    )
    return {
        "transition": result["transition"].to_dict(),
        "output_node": result["output_node"].to_dict(),
        "payload": result["payload"].to_dict(),
        "exit_code": result["exit_code"],
    }


def cli_command(args) -> int:
    try:
        if args.command_command == "run":
            argv = _strip_separator(list(args.argv))
            if not argv:
                print("error: command run requires a command after --", file=sys.stderr)
                return 2
            result = run_command_run_command(
                run_id=resolve_run_id_from_args(args),
                store_dir=args.store_dir,
                argv=argv,
                cwd=args.cwd,
                user_id=resolve_user_id_from_args(args),
                work_session_id=resolve_work_session_id_from_args(args),
                max_output_chars=args.max_output_chars,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return int(result["exit_code"])
        print(f"unknown command subcommand: {args.command_command}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _strip_separator(argv: list[str]) -> list[str]:
    if argv and argv[0] == "--":
        return argv[1:]
    return argv
