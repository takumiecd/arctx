"""User-facing arctx attach command."""

from __future__ import annotations

import argparse
import json
import sys

from arctx_cli.commands._targets import resolve_target_kind
from arctx_cli.commands.payload import run_payload_add_command
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)
from arctx_cli.payload_builder import parse_field_args, parse_json_object


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("attach", help="Attach a Payload to a Node or Step")
    parser.add_argument("target_id")
    parser.add_argument("--type", dest="payload_kind", default="payload")
    parser.add_argument("--payload-type", default=None)
    parser.add_argument("--field", action="append", default=None, help="Payload field as key=value")
    parser.add_argument("--json", default=None, help="Payload fields as a JSON object")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--work-session", default=None)
    return parser


def run_attach_command(
    *,
    run_id: str,
    target_id: str,
    payload_kind: str,
    payload_type: str | None,
    field_data: dict,
    json_data: dict,
    store_dir: str,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    target_kind = resolve_target_kind(handle, target_id)
    if target_kind == "payload":
        raise ValueError("cannot attach a payload to another payload")

    data = dict(json_data or {})
    data.update(field_data or {})
    data.setdefault("type", payload_kind)
    internal_payload_type = payload_type or (
        "node_payload" if target_kind == "node" else "transition_payload"
    )
    result = run_payload_add_command(
        run_id=run_id,
        target_kind=target_kind,
        target_id=target_id,
        payload_type=internal_payload_type,
        field_data=data,
        json_data={},
        store_dir=store_dir,
        user_id=user_id,
        work_session_id=work_session_id,
    )
    return result


def cli_attach(args) -> int:
    try:
        result = run_attach_command(
            run_id=resolve_run_id_from_args(args),
            target_id=args.target_id,
            payload_kind=args.payload_kind,
            payload_type=args.payload_type,
            field_data=parse_field_args(args.field),
            json_data=parse_json_object(args.json),
            store_dir=args.store_dir,
            user_id=resolve_user_id_from_args(args),
            work_session_id=resolve_work_session_id_from_args(args),
        )
        print(json.dumps(result["payload"], ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
