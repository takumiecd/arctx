"""arctx-native sync CLI: ``remote`` / ``push`` / ``pull``.

Modeled on git's UX, but simpler because the DAG is a CRDT: push sends the
records the remote lacks (id diff), pull unions the remote's records into the
local graph (idempotent, no conflicts, no history rewrite). This is arctx's OWN
transport (file-backed shared append-log) — git is only the mental model, not the
mechanism.

v1 transport is a local file remote (a shared directory). The PR/accept gate
(`arctx accept`) runs on top: pull records in, then the target owner accepts or
rejects.
"""

from __future__ import annotations

import argparse
import json
import sys

from arctx.core.sync.local import (
    default_remote_dir,
    load_sync_config,
    sync_init,
    sync_pull,
    sync_push,
    sync_status,
)

from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_lane_id_from_args,
)
from arctx_cli.paths import resolve_store_dir


def _store_and_handle(run_id, store_dir):
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    return store, store.load_run(run_id), store.run_path(run_id)


# ---------------------------------------------------------------------------
# remote
# ---------------------------------------------------------------------------


def run_remote_add_command(*, run_id, name, remote_dir, shared_run_id, store_dir,
                           user_id=None, lane_id=None):
    """Register a remote for this run (file-backed shared append-log)."""
    store, handle, run_path = _store_and_handle(run_id, store_dir)
    rd = remote_dir or str(default_remote_dir(store_dir or resolve_store_dir()))
    return sync_init(
        handle=handle, run_path=run_path, remote=name,
        shared_run_id=shared_run_id or run_id, remote_dir=rd,
        workspace_id=lane_id or "default", actor_id=user_id or "anon",
    )


def run_remote_show_command(*, run_id, store_dir):
    """Show the run's configured remote + push/pull status."""
    store, handle, run_path = _store_and_handle(run_id, store_dir)
    cfg = load_sync_config(run_path)
    status = sync_status(handle=handle, remote=cfg["remote"],
                         shared_run_id=cfg["shared_run_id"],
                         remote_dir=cfg["remote_dir"])
    return {"remote": cfg, "status": status}


# ---------------------------------------------------------------------------
# push / pull
# ---------------------------------------------------------------------------


def run_push_command(*, run_id, store_dir):
    """Send local records the remote lacks (id diff, idempotent)."""
    store, handle, run_path = _store_and_handle(run_id, store_dir)
    cfg = load_sync_config(run_path)
    return sync_push(
        handle=handle, remote=cfg["remote"], shared_run_id=cfg["shared_run_id"],
        remote_dir=cfg["remote_dir"], workspace_id=cfg["workspace_id"],
        actor_id=cfg["actor_id"],
    )


def run_pull_command(*, run_id, store_dir):
    """Union the remote's records into the local graph, then persist."""
    store, handle, run_path = _store_and_handle(run_id, store_dir)
    cfg = load_sync_config(run_path)
    res = sync_pull(handle=handle, remote=cfg["remote"],
                    shared_run_id=cfg["shared_run_id"], remote_dir=cfg["remote_dir"])
    store.save_run(handle)  # persist pulled records
    return res


# ---------------------------------------------------------------------------
# parsers / dispatch
# ---------------------------------------------------------------------------


def add_remote_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``remote`` command."""
    p = subparsers.add_parser("remote", help="Configure/show the sync remote")
    p.add_argument("action", nargs="?", choices=["add"], help="`add` to register a remote")
    p.add_argument("name", nargs="?", help="Remote name (e.g. origin)")
    p.add_argument("dir", nargs="?", help="Remote directory (file-backed shared log)")
    p.add_argument("--shared-run", dest="shared_run", default=None,
                   help="Run id on the remote (default: this run id)")
    p.add_argument("--run", default=None)
    p.add_argument("--store-dir", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--lane", default=None)
    return p


def add_push_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``push`` command."""
    p = subparsers.add_parser("push", help="Push local records to the remote (id diff)")
    p.add_argument("remote", nargs="?", help="Remote name (default: configured)")
    p.add_argument("--run", default=None)
    p.add_argument("--store-dir", default=None)
    return p


def add_pull_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``pull`` command."""
    p = subparsers.add_parser("pull", help="Pull remote records and union them in")
    p.add_argument("remote", nargs="?", help="Remote name (default: configured)")
    p.add_argument("--run", default=None)
    p.add_argument("--store-dir", default=None)
    return p


def cli_remote(args) -> int:
    """Dispatch ``remote`` (add / show)."""
    try:
        if args.action == "add":
            if not args.name:
                raise ValueError("usage: arctx remote add NAME [DIR]")
            result = run_remote_add_command(
                run_id=resolve_run_id_from_args(args), name=args.name,
                remote_dir=args.dir, shared_run_id=args.shared_run,
                store_dir=args.store_dir, user_id=resolve_user_id_from_args(args),
                lane_id=resolve_lane_id_from_args(args),
            )
        else:
            result = run_remote_show_command(
                run_id=resolve_run_id_from_args(args), store_dir=args.store_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def cli_push(args) -> int:
    """Dispatch ``push``."""
    try:
        result = run_push_command(run_id=resolve_run_id_from_args(args),
                                  store_dir=args.store_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def cli_pull(args) -> int:
    """Dispatch ``pull``."""
    try:
        result = run_pull_command(run_id=resolve_run_id_from_args(args),
                                  store_dir=args.store_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
