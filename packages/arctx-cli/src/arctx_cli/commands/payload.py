"""arctx payload commands."""

from __future__ import annotations

import argparse
import json

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)
from arctx_cli.payload_builder import (
    build_payload,
    parse_field_args,
    parse_json_object,
    payload_schema,
    payload_type_names,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("payload", help="Inspect and attach payloads")
    payload_sub = parser.add_subparsers(dest="payload_command", required=True)

    sp_types = payload_sub.add_parser("types", help="List registered payload types")
    sp_types.add_argument("--store-dir", default=None)

    sp_schema = payload_sub.add_parser("schema", help="Show payload type fields")
    sp_schema.add_argument("payload_type")
    sp_schema.add_argument("--store-dir", default=None)

    sp_add = payload_sub.add_parser("add", help="Attach a payload to a node or transition")
    target = sp_add.add_mutually_exclusive_group(required=True)
    target.add_argument("--node", dest="node_id", default=None)
    target.add_argument("--transition", dest="transition_id", default=None)
    sp_add.add_argument("--payload-type", required=True)
    sp_add.add_argument("--field", action="append", default=None, help="Payload field as key=value")
    sp_add.add_argument("--json", default=None, help="Payload fields as a JSON object")
    sp_add.add_argument("--run", default=None)
    sp_add.add_argument("--store-dir", default=None)
    sp_add.add_argument("--user", default=None)
    sp_add.add_argument("--work-session", default=None)

    sp_list = payload_sub.add_parser("list", help="List payloads on a node or transition")
    target = sp_list.add_mutually_exclusive_group(required=True)
    target.add_argument("--node", dest="node_id", default=None)
    target.add_argument("--transition", dest="transition_id", default=None)
    sp_list.add_argument("--run", default=None)
    sp_list.add_argument("--store-dir", default=None)

    sp_show = payload_sub.add_parser("show", help="Show one payload")
    sp_show.add_argument("payload_id")
    sp_show.add_argument("--run", default=None)
    sp_show.add_argument("--store-dir", default=None)

    return parser


def run_payload_add_command(
    *,
    run_id: str,
    target_kind: str,
    target_id: str,
    payload_type: str,
    field_data: dict | None,
    json_data: dict | None,
    store_dir: str,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    before = graph_counts(handle)
    payload = build_payload(
        payload_type=payload_type,
        target_kind=target_kind,  # type: ignore[arg-type]
        target_id=target_id,
        payload_id=handle._next_id("pl"),
        json_data=json_data,
        field_data=field_data,
    )
    if payload.target_kind == "node":
        attached = handle.attach(
            payload.target_id,
            payload,
            user_id=user_id,
            work_session_id=work_session_id,
        )
    else:
        handle.run_graph.attach_payload(payload)
        handle.record_work_event(
            user_id=user_id,
            work_session_id=work_session_id,
            event_type="payload_attached",
            target_kind="transition",
            target_id=payload.target_id,
            created_records=(payload.payload_id,),
            summary=payload.payload_type,
        )
        attached = payload
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=work_session_id,
        before=before,
    )
    return {"payload": attached.to_dict()}


def run_payload_list_command(
    *,
    run_id: str,
    target_kind: str,
    target_id: str,
    store_dir: str,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    g = handle.run_graph
    if target_kind == "node":
        if target_id not in g.nodes:
            raise KeyError(f"unknown node_id: {target_id}")
        payloads = g.payloads_for_node(target_id)
    else:
        if target_id not in g.transitions:
            raise KeyError(f"unknown transition_id: {target_id}")
        payloads = g.payloads_for_transition(target_id)
    return {"payloads": [p.to_dict() for p in payloads]}


def run_payload_show_command(*, run_id: str, payload_id: str, store_dir: str) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    payload = handle.run_graph.payloads.get(payload_id)
    if payload is None:
        raise KeyError(f"unknown payload_id: {payload_id}")
    return {"payload": payload.to_dict()}


def cli_payload(args) -> int:
    if args.payload_command == "types":
        print(json.dumps({"payload_types": payload_type_names()}, ensure_ascii=False, indent=2))
        return 0
    if args.payload_command == "schema":
        print(json.dumps(payload_schema(args.payload_type), ensure_ascii=False, indent=2))
        return 0
    if args.payload_command == "add":
        target_kind = "node" if args.node_id is not None else "transition"
        target_id = args.node_id if args.node_id is not None else args.transition_id
        result = run_payload_add_command(
            run_id=resolve_run_id_from_args(args),
            target_kind=target_kind,
            target_id=target_id,
            payload_type=args.payload_type,
            field_data=parse_field_args(args.field),
            json_data=parse_json_object(args.json),
            store_dir=args.store_dir,
            user_id=resolve_user_id_from_args(args),
            work_session_id=resolve_work_session_id_from_args(args),
        )
        print(json.dumps(result["payload"], ensure_ascii=False, indent=2))
        return 0
    if args.payload_command == "list":
        target_kind = "node" if args.node_id is not None else "transition"
        target_id = args.node_id if args.node_id is not None else args.transition_id
        result = run_payload_list_command(
            run_id=resolve_run_id_from_args(args),
            target_kind=target_kind,
            target_id=target_id,
            store_dir=args.store_dir,
        )
        print(json.dumps(result["payloads"], ensure_ascii=False, indent=2))
        return 0
    if args.payload_command == "show":
        result = run_payload_show_command(
            run_id=resolve_run_id_from_args(args),
            payload_id=args.payload_id,
            store_dir=args.store_dir,
        )
        print(json.dumps(result["payload"], ensure_ascii=False, indent=2))
        return 0
    return 1
