"""arctx CLI transition command."""

from __future__ import annotations

import argparse
import json
import sys

from arctx_cli.commands.outcomes import run_outcomes_command
from arctx_cli.commands.show import run_show_command
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)
from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.payload_builder import build_payload, parse_field_args, parse_json_object
from arctx.core.schema.payloads import TransitionPayload


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "transition",
        help="Create and inspect transitions",
    )
    transition_sub = parser.add_subparsers(dest="transition_command", required=True)

    sp_create = transition_sub.add_parser(
        "create",
        help="Create one Transition and one output Node from input nodes",
    )
    sp_create.add_argument("--run", default=None)
    sp_create.add_argument(
        "--from",
        action="append",
        required=True,
        dest="input_nodes",
        metavar="NODE_ID",
        help="Input node (repeatable for multi-node transitions)",
    )
    sp_create.add_argument("--payload-type", default="transition_payload")
    sp_create.add_argument("--field", action="append", default=None, help="Payload field as key=value")
    sp_create.add_argument("--json", default=None, help="Payload fields as a JSON object")
    sp_create.add_argument("--store-dir", default=None)
    sp_create.add_argument("--user", default=None)
    sp_create.add_argument("--work-session", default=None)

    sp_show = transition_sub.add_parser("show", help="Show one transition")
    sp_show.add_argument("transition_id")
    sp_show.add_argument("--with-payloads", action="store_true")
    sp_show.add_argument("--run", default=None)
    sp_show.add_argument("--store-dir", default=None)

    sp_output = transition_sub.add_parser("output", help="Show a transition output node")
    sp_output.add_argument("transition_id")
    sp_output.add_argument("--run", default=None)
    sp_output.add_argument("--store-dir", default=None)

    sp_inputs = transition_sub.add_parser("inputs", help="Show transition input nodes")
    sp_inputs.add_argument("transition_id")
    sp_inputs.add_argument("--run", default=None)
    sp_inputs.add_argument("--store-dir", default=None)

    sp_payloads = transition_sub.add_parser("payloads", help="Show transition payloads")
    sp_payloads.add_argument("transition_id")
    sp_payloads.add_argument("--run", default=None)
    sp_payloads.add_argument("--store-dir", default=None)
    return parser


def run_transition_command(
    *,
    run_id: str,
    input_node_ids: list[str],
    payload_type: str,
    content: dict,
    store_dir: str,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    payload = TransitionPayload(
        payload_id="pending",
        target_id="pending",
        type=payload_type,
        content=content,
    )
    before = graph_counts(handle)
    transition = handle.transition(
        input_node_ids,
        payload,
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
    return {"transition": transition.to_dict()}


def run_transition_create_command(
    *,
    run_id: str,
    input_node_ids: list[str],
    payload_type: str,
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
    payload = build_payload(
        payload_type=payload_type,
        target_kind="transition",
        target_id="pending",
        payload_id="pending",
        json_data=json_data,
        field_data=field_data,
    )
    before = graph_counts(handle)
    transition = handle.transition(
        input_node_ids,
        payload,
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
    return {"transition": transition.to_dict()}


def cli_transition(args) -> int:
    try:
        if args.transition_command == "create":
            result = run_transition_create_command(
                run_id=resolve_run_id_from_args(args),
                input_node_ids=args.input_nodes,
                payload_type=args.payload_type,
                field_data=parse_field_args(args.field),
                json_data=parse_json_object(args.json),
                store_dir=args.store_dir,
                user_id=resolve_user_id_from_args(args),
                work_session_id=resolve_work_session_id_from_args(args),
            )
            print(json.dumps(result["transition"], ensure_ascii=False, indent=2))
            return 0
        if args.transition_command == "show":
            result = run_show_command(
                run_id=resolve_run_id_from_args(args),
                node_id=None,
                transition_id=args.transition_id,
                payload_id=None,
                with_payloads=args.with_payloads,
                outputs=True,
                store_dir=args.store_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.transition_command == "output":
            result = run_outcomes_command(
                run_id=resolve_run_id_from_args(args),
                transition_id=args.transition_id,
                include_payloads=False,
                store_dir=args.store_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.transition_command == "inputs":
            result = run_show_command(
                run_id=resolve_run_id_from_args(args),
                node_id=None,
                transition_id=args.transition_id,
                payload_id=None,
                with_payloads=False,
                outputs=False,
                store_dir=args.store_dir,
            )
            print(json.dumps({"input_node_ids": result["input_node_ids"]}, ensure_ascii=False, indent=2))
            return 0
        if args.transition_command == "payloads":
            result = run_show_command(
                run_id=resolve_run_id_from_args(args),
                node_id=None,
                transition_id=args.transition_id,
                payload_id=None,
                with_payloads=True,
                outputs=False,
                store_dir=args.store_dir,
            )
            print(json.dumps(result["payloads"], ensure_ascii=False, indent=2))
            return 0
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
