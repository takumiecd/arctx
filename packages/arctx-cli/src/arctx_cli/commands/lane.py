"""arctx CLI ``lane`` command — the active work-context, ``git switch`` style.

A **lane** is a solo-or-collaborative, append-only unit of work. Usage mirrors
``source .venv`` / ``git switch``:

    arctx lane geometry        # switch to (create) lane "geometry" — persists
                               # across shells via <gitdir>/arctx-lane, no eval
    arctx lane                 # show the current lane
    arctx lane --list          # list lanes in the run
    eval "$(arctx lane geometry --shell)"   # shell-local pin, for PARALLEL work
                                            # (env beats the file pointer)

A lane is NOT owned by one user: any actor may switch to a shared lane; per-action
attribution lives on each event. Persistent (file pointer) is the default; the
``--shell`` env override is the opt-in needed only when running explorations in
parallel from several terminals.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from arctx.core.append import AppendBatch

from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
)
from arctx_cli.paths import (
    arctx_lane_path,
    find_repo_root,
    read_arctx_lane,
    write_arctx_lane,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``lane`` command (flat: name = switch, no name = current)."""
    parser = subparsers.add_parser(
        "lane",
        help="Switch/show the active lane (solo or collaborative unit of work)",
        description=(
            "`arctx lane NAME` switches to (creates) a lane and pins it for this "
            "checkout via <gitdir>/arctx-lane — it persists across shells, no eval. "
            "`arctx lane` shows the current lane. For PARALLEL work in separate "
            'terminals, use `eval "$(arctx lane NAME --shell)"` (env beats the file).'
        ),
    )
    parser.add_argument("name", nargs="?", help="Lane name to switch to / create")
    parser.add_argument("--list", action="store_true", dest="list_lanes",
                        help="List lanes in the run")
    parser.add_argument("--shell", action="store_true",
                        help="Print an export line for shell-local (parallel) use "
                             "instead of writing the persistent pointer")
    parser.add_argument("--user", default=None, help="Actor (created_by) when creating")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _find_lane_by_name(handle, name: str):
    for session in handle.run_graph.work_sessions.values():
        if session.name == name:
            return session
    return None


def run_lane_switch_command(
    *, name: str, run_id: str, user_id: str, store_dir: str | None, shell: bool = False,
) -> dict:
    """Switch to a lane by name (creating it if new), returning a result dict.

    Persistent mode writes ``<gitdir>/arctx-lane``; ``shell`` mode returns an
    ``export`` line instead (terminal-scoped, for parallel work).
    """
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    existing = _find_lane_by_name(handle, name)
    if existing is not None:
        lane = existing
        created = False
    else:
        lane = handle.ensure_lane(name=name, created_by=user_id)
        created = True
        if hasattr(store, "append_batch"):
            store.append_batch(
                AppendBatch(
                    run_id=run_id,
                    user_id=user_id or "",
                    work_session_id=lane.work_session_id,
                    work_session=lane,
                    records=(),
                    events=(),
                )
            )
        else:
            store.save_run(handle)

    result = {"lane_id": lane.work_session_id, "name": name, "created": created}
    if shell:
        result["export"] = (
            f"export ARCTX_LANE_ID={lane.work_session_id}; "
            f"export ARCTX_WORK_SESSION_ID={lane.work_session_id}"
        )
    else:
        repo_root = find_repo_root()
        write_arctx_lane(repo_root, lane.work_session_id, run_id=run_id)
        result["arctx_lane_path"] = str(arctx_lane_path(repo_root))
    return result


def run_lane_current_command(*, run_id: str, store_dir: str | None) -> dict:
    """Resolve the active lane (env > file pointer) and return its id/name."""
    lane_id = os.environ.get("ARCTX_LANE_ID") or os.environ.get("ARCTX_WORK_SESSION_ID")
    source = "env"
    if not lane_id:
        try:
            lane_id = read_arctx_lane(find_repo_root(), run_id=run_id)
            source = "pointer"
        except RuntimeError:
            lane_id = None
    if not lane_id:
        return {"lane_id": None, "name": None, "source": "default"}
    name = None
    store = resolve_store(store_dir)
    if store.run_path(run_id).exists():
        handle = store.load_run(run_id)
        lane = handle.run_graph.work_sessions.get(lane_id)
        name = lane.name if lane is not None else None
    return {"lane_id": lane_id, "name": name, "source": source}


def list_lanes(*, run_id: str, store_dir: str | None) -> list[dict]:
    """Return all lanes in the run under lane vocabulary."""
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    sessions = sorted(
        handle.run_graph.work_sessions.values(),
        key=lambda s: (s.started_at or "", s.work_session_id),
    )
    return [
        {
            "lane_id": s.work_session_id,
            "name": s.name,
            "created_by": s.user_id,
            "parent_lane_id": s.parent_work_session_id,
            "status": s.status,
        }
        for s in sessions
    ]


def cli_lane(args) -> int:
    """Dispatch ``lane``: --list, NAME (switch), or bare (current)."""
    try:
        if args.list_lanes:
            lanes = list_lanes(run_id=resolve_run_id_from_args(args),
                               store_dir=args.store_dir)
            print(json.dumps({"lanes": lanes}, ensure_ascii=False, indent=2))
            return 0

        if args.name:
            result = run_lane_switch_command(
                name=args.name,
                run_id=resolve_run_id_from_args(args),
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
                shell=args.shell,
            )
            if args.shell:
                print(result["export"])
            elif args.as_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(result["name"])
            return 0

        # bare `arctx lane` → show current
        result = run_lane_current_command(
            run_id=resolve_run_id_from_args(args), store_dir=args.store_dir
        )
        if args.as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["name"] or result["lane_id"] or "(default)")
        return 0
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
