"""arctx CLI cut command."""

from __future__ import annotations

import argparse
import json

from arctx_cli.commands._targets import resolve_target_kind
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)
from arctx_cli.append_batch import graph_counts, maybe_append_or_save


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("cut", help="Cut a Node or Transition")
    parser.add_argument("kind", nargs="?")
    parser.add_argument("id", nargs="?")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--node", dest="node_id", metavar="NODE_ID")
    group.add_argument("--transition", dest="transition_id", metavar="TRANSITION_ID")
    parser.add_argument("--run", default=None)
    parser.add_argument("--reason", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--work-session", default=None)
    return parser


def run_cut_command(
    *,
    run_id: str,
    target_id: str,
    target_kind: str,
    reason: str | None,
    store_dir: str,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    before = graph_counts(handle)
    cut = handle.cut(
        target_id,
        target_kind=target_kind,  # type: ignore[arg-type]
        reason=reason,
        user_id=user_id,
        work_session_id=work_session_id,
    )
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=work_session_id,
        before=before,
    )
    return {"cut": cut.to_dict()}


def cli_cut(args) -> int:
    run_id = resolve_run_id_from_args(args)
    store_dir = args.store_dir
    if args.node_id is not None:
        target_id = args.node_id
        target_kind = "node"
    elif args.transition_id is not None:
        target_id = args.transition_id
        target_kind = "transition"
    elif args.kind is not None and args.id is not None:
        if args.kind not in ("node", "transition", "step"):
            raise ValueError("cut target kind must be node, transition, or step")
        target_id = args.id
        target_kind = "transition" if args.kind == "step" else args.kind
    elif args.kind is not None:
        target_id = args.kind
        store = resolve_store(store_dir)
        if not store.run_path(run_id).exists():
            raise KeyError(f"unknown run_id: {run_id}")
        handle = store.load_run(run_id)
        resolved = resolve_target_kind(handle, target_id)
        if resolved == "payload":
            raise ValueError("cannot cut a payload")
        target_kind = resolved
    else:
        raise ValueError("provide '<id>', 'node <id>', 'transition <id>', --node, or --transition")

    result = run_cut_command(
        run_id=run_id,
        target_id=target_id,
        target_kind=target_kind,
        reason=args.reason,
        store_dir=args.store_dir,
        user_id=resolve_user_id_from_args(args),
        work_session_id=resolve_work_session_id_from_args(args),
    )
    print(json.dumps(result["cut"], ensure_ascii=False, indent=2))
    return 0
