"""arctx asset command — attach and manage file assets (core payload)."""

from __future__ import annotations

import argparse
import json
import sys

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_lane_id_from_args,
)
from arctx_cli.lane_gate import ensure_lane_open


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``asset`` command namespace."""
    asset_parser = subparsers.add_parser("asset", help="Asset management commands")
    asset_sub = asset_parser.add_subparsers(dest="asset_command", required=True)

    sp_attach = asset_sub.add_parser("attach", help="Attach a file to a Node or Step")
    sp_attach.add_argument("file_path", help="Path to the file to attach")
    sp_attach.add_argument("--target", required=True, dest="target_id", help="Node or Step ID")
    sp_attach.add_argument("--run", default=None)
    sp_attach.add_argument("--store-dir", default=None)
    sp_attach.add_argument("--user", default=None)
    sp_attach.add_argument("--lane", default=None)
    sp_attach.add_argument("--force", action="store_true",
                           help="Write even if the target lane is closed")

    sp_list = asset_sub.add_parser("list", help="List assets for a Node or Step")
    sp_list.add_argument("--target", required=True, dest="target_id", help="Node or Step ID")
    sp_list.add_argument("--run", default=None)
    sp_list.add_argument("--store-dir", default=None)

    sp_show = asset_sub.add_parser("show", help="Show details of a specific asset payload")
    sp_show.add_argument("payload_id", help="Payload ID of the asset")
    sp_show.add_argument("--run", default=None)
    sp_show.add_argument("--store-dir", default=None)

    return asset_parser


def cli_asset(args) -> int:
    """Dispatch ``arctx asset`` subcommands."""
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
    lane_id = resolve_lane_id_from_args(args)

    if not store.run_path(run_id).exists():
        print(f"error: unknown run_id: {run_id}", file=sys.stderr)
        return 1

    handle = store.load_run(run_id)
    if (
        args.target_id not in handle.run_graph.nodes
        and args.target_id not in handle.run_graph.steps
    ):
        print(f"error: target_id not found: {args.target_id}", file=sys.stderr)
        return 1

    try:
        ensure_lane_open(handle, lane_id, force=args.force)
        before = graph_counts(handle)
        payload = handle.attach_asset(
            args.target_id,
            args.file_path,
            user_id=user_id,
            lane_id=lane_id,
        )
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane_id,
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
    if args.target_id in handle.run_graph.nodes:
        raw_payloads = handle.run_graph.payloads_for_node(args.target_id)
    elif args.target_id in handle.run_graph.steps:
        raw_payloads = handle.run_graph.payloads_for_step(args.target_id)
    else:
        print(f"error: target_id not found: {args.target_id}", file=sys.stderr)
        return 1

    payloads = [
        p.to_dict()
        for p in raw_payloads
        if getattr(p, "payload_type", None) == "asset"
    ]
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
