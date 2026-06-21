"""arctx asset subcommand — attach and manage file assets."""

from __future__ import annotations

import argparse
import json
import sys

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``asset`` command namespace."""
    asset_parser = subparsers.add_parser("asset", help="Asset management commands")
    asset_sub = asset_parser.add_subparsers(dest="asset_command", required=True)

    # attach
    sp_attach = asset_sub.add_parser("attach", help="Attach a file to a Node or Step")
    sp_attach.add_argument("file_path", help="Path to the file to attach")
    sp_attach.add_argument("--target", required=True, dest="target_id", help="Node or Step ID")
    sp_attach.add_argument("--run", default=None)
    sp_attach.add_argument("--store-dir", default=None)
    sp_attach.add_argument("--user", default=None)
    sp_attach.add_argument("--work-session", default=None)

    # list
    sp_list = asset_sub.add_parser("list", help="List assets for a Node or Step")
    sp_list.add_argument("--target", required=True, dest="target_id", help="Node or Step ID")
    sp_list.add_argument("--run", default=None)
    sp_list.add_argument("--store-dir", default=None)

    # show
    sp_show = asset_sub.add_parser("show", help="Show details of a specific asset payload")
    sp_show.add_argument("payload_id", help="Payload ID of the asset")
    sp_show.add_argument("--run", default=None)
    sp_show.add_argument("--store-dir", default=None)

    return asset_parser


def cli_asset(args) -> int:
    """Dispatch canonical ``arctx asset`` subcommands."""
    if args.asset_command == "attach":
        return _cli_asset_attach(args)
    if args.asset_command == "list":
        return _cli_asset_list(args)
    if args.asset_command == "show":
        return _cli_asset_show(args)
    print(f"unknown asset subcommand: {args.asset_command}", file=sys.stderr)
    return 1


def _cli_asset_attach(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    work_session_id = resolve_work_session_id_from_args(args)

    if not store.run_path(run_id).exists():
        print(f"error: unknown run_id: {run_id}", file=sys.stderr)
        return 1

    handle = store.load_run(run_id)

    # Make sure target exists
    if (
        args.target_id not in handle.run_graph.nodes
        and args.target_id not in handle.run_graph.steps
    ):
        print(f"error: target_id not found: {args.target_id}", file=sys.stderr)
        return 1

    try:
        before = graph_counts(handle)
        # Call the extension verb
        payload = handle.asset.attach(
            args.target_id,
            args.file_path,
            user_id=user_id,
            work_session_id=work_session_id,
        )
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=work_session_id,
        before=before,
    )
    print(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _cli_asset_list(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)

    if not store.run_path(run_id).exists():
        print(f"error: unknown run_id: {run_id}", file=sys.stderr)
        return 1

    handle = store.load_run(run_id)

    # Filter payloads by type 'asset' and target_id
    payloads = []
    # Both Node and Step can have payloads
    if args.target_id in handle.run_graph.nodes:
        raw_payloads = handle.run_graph.payloads_for_node(args.target_id)
    elif args.target_id in handle.run_graph.steps:
        raw_payloads = handle.run_graph.payloads_for_step(args.target_id)
    else:
        print(f"error: target_id not found: {args.target_id}", file=sys.stderr)
        return 1

    for p in raw_payloads:
        if getattr(p, "payload_type", None) == "asset":
            payloads.append(p.to_dict())

    print(json.dumps(payloads, ensure_ascii=False, indent=2))
    return 0


def _cli_asset_show(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)

    if not store.run_path(run_id).exists():
        print(f"error: unknown run_id: {run_id}", file=sys.stderr)
        return 1

    handle = store.load_run(run_id)
    payload = handle.run_graph.payloads.get(args.payload_id)
    if payload is None or getattr(payload, "payload_type", None) != "asset":
        print(f"error: asset payload not found: {args.payload_id}", file=sys.stderr)
        return 1

    print(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2))
    return 0
