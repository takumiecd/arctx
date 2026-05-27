"""arctx CLI sync command."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from arctx_cli.context import resolve_run_id_from_args, resolve_store, resolve_user_id_from_args


def _sync_local():
    from arctx.core.sync import local

    return local


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "sync",
        help="Synchronize a local run with a file-backed shared DAG",
    )
    commands = parser.add_subparsers(dest="sync_command", required=True)

    init = commands.add_parser("init", help="Initialize sync for a local run")
    _add_common_args(init)
    init.add_argument("--shared-run", required=True, dest="shared_run_id")
    init.add_argument("--workspace", default=None, dest="workspace_id")
    init.add_argument("--user", default=None)

    status = commands.add_parser("status", help="Show local/shared sync status")
    _add_common_args(status)
    status.add_argument("--shared-run", default=None, dest="shared_run_id")

    push = commands.add_parser("push", help="Push local records to the shared DAG")
    _add_common_args(push)
    push.add_argument("--shared-run", default=None, dest="shared_run_id")
    push.add_argument("--workspace", default=None, dest="workspace_id")
    push.add_argument("--user", default=None)

    pull = commands.add_parser("pull", help="Pull shared DAG records into the local run")
    _add_common_args(pull)
    pull.add_argument("--shared-run", default=None, dest="shared_run_id")

    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--remote", default=None)
    parser.add_argument("--remote-dir", default=None)


def run_sync_init_command(
    *,
    run_id: str,
    shared_run_id: str,
    store_dir: str,
    remote: str = "local-shared",
    remote_dir: str | None = None,
    workspace_id: str | None = None,
    actor_id: str = "user",
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    sync = _sync_local()
    return sync.sync_init(
        handle=handle,
        run_path=store.run_path(run_id),
        remote=remote,
        shared_run_id=shared_run_id,
        remote_dir=remote_dir or str(sync.default_remote_dir(store_dir)),
        workspace_id=workspace_id or _default_workspace_id(),
        actor_id=actor_id,
    )


def run_sync_status_command(
    *,
    run_id: str,
    store_dir: str,
    shared_run_id: str | None = None,
    remote: str | None = None,
    remote_dir: str | None = None,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    cfg = _resolve_sync_config(
        run_path=store.run_path(run_id),
        shared_run_id=shared_run_id,
        remote=remote,
        remote_dir=remote_dir,
        store_dir=store_dir,
    )
    sync = _sync_local()
    return sync.sync_status(
        handle=handle,
        remote=cfg["remote"],
        shared_run_id=cfg["shared_run_id"],
        remote_dir=cfg["remote_dir"],
    )


def run_sync_push_command(
    *,
    run_id: str,
    store_dir: str,
    shared_run_id: str | None = None,
    remote: str | None = None,
    remote_dir: str | None = None,
    workspace_id: str | None = None,
    actor_id: str = "user",
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    cfg = _resolve_sync_config(
        run_path=store.run_path(run_id),
        shared_run_id=shared_run_id,
        remote=remote,
        remote_dir=remote_dir,
        store_dir=store_dir,
    )
    sync = _sync_local()
    return sync.sync_push(
        handle=handle,
        remote=cfg["remote"],
        shared_run_id=cfg["shared_run_id"],
        remote_dir=cfg["remote_dir"],
        workspace_id=workspace_id or cfg.get("workspace_id") or _default_workspace_id(),
        actor_id=actor_id,
    )


def run_sync_pull_command(
    *,
    run_id: str,
    store_dir: str,
    shared_run_id: str | None = None,
    remote: str | None = None,
    remote_dir: str | None = None,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    cfg = _resolve_sync_config(
        run_path=store.run_path(run_id),
        shared_run_id=shared_run_id,
        remote=remote,
        remote_dir=remote_dir,
        store_dir=store_dir,
    )
    sync = _sync_local()
    result = sync.sync_pull(
        handle=handle,
        remote=cfg["remote"],
        shared_run_id=cfg["shared_run_id"],
        remote_dir=cfg["remote_dir"],
    )
    store.save_run(handle)
    return result


def cli_sync(args) -> int:
    if args.sync_command == "init":
        result = run_sync_init_command(
            run_id=resolve_run_id_from_args(args),
            shared_run_id=args.shared_run_id,
            store_dir=args.store_dir,
            remote=args.remote or "local-shared",
            remote_dir=args.remote_dir,
            workspace_id=args.workspace_id,
            actor_id=resolve_user_id_from_args(args),
        )
    elif args.sync_command == "status":
        result = run_sync_status_command(
            run_id=resolve_run_id_from_args(args),
            store_dir=args.store_dir,
            shared_run_id=args.shared_run_id,
            remote=args.remote,
            remote_dir=args.remote_dir,
        )
    elif args.sync_command == "push":
        result = run_sync_push_command(
            run_id=resolve_run_id_from_args(args),
            store_dir=args.store_dir,
            shared_run_id=args.shared_run_id,
            remote=args.remote,
            remote_dir=args.remote_dir,
            workspace_id=args.workspace_id,
            actor_id=resolve_user_id_from_args(args),
        )
    elif args.sync_command == "pull":
        result = run_sync_pull_command(
            run_id=resolve_run_id_from_args(args),
            store_dir=args.store_dir,
            shared_run_id=args.shared_run_id,
            remote=args.remote,
            remote_dir=args.remote_dir,
        )
    else:
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _resolve_sync_config(
    *,
    run_path: Path,
    shared_run_id: str | None,
    remote: str | None,
    remote_dir: str | None,
    store_dir: str,
) -> dict[str, str]:
    if shared_run_id is None or remote is None or remote_dir is None:
        try:
            cfg = _sync_local().load_sync_config(run_path)
        except RuntimeError:
            if shared_run_id is None:
                raise
            cfg = {}
    else:
        cfg = {}
    return {
        "shared_run_id": shared_run_id or cfg["shared_run_id"],
        "remote": remote or cfg.get("remote", "local-shared"),
        "remote_dir": remote_dir
        or cfg.get("remote_dir", str(_sync_local().default_remote_dir(store_dir))),
        "workspace_id": cfg.get("workspace_id", _default_workspace_id()),
        "actor_id": cfg.get("actor_id", "user"),
    }


def _default_workspace_id() -> str:
    return os.environ.get("ARCTX_WORKSPACE_ID") or "local"
