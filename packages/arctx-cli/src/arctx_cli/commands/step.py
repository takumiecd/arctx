"""arctx CLI step command."""

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
from arctx.core.schema.payloads import StepPayload


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "step",
        help="Create and inspect steps",
    )
    step_sub = parser.add_subparsers(dest="step_command", required=True)

    sp_create = step_sub.add_parser(
        "create",
        help="Create one Step and one output Node from input nodes",
    )
    sp_create.add_argument("--run", default=None)
    sp_create.add_argument(
        "--from",
        action="append",
        required=True,
        dest="input_nodes",
        metavar="NODE_ID",
        help="Input node (repeatable for multi-node steps)",
    )
    sp_create.add_argument("--payload-type", default="step_payload")
    sp_create.add_argument("--field", action="append", default=None, help="Payload field as key=value")
    sp_create.add_argument("--json", default=None, help="Payload fields as a JSON object")
    sp_create.add_argument("--store-dir", default=None)
    sp_create.add_argument("--user", default=None)
    sp_create.add_argument("--work-session", default=None)

    sp_show = step_sub.add_parser("show", help="Show one step")
    sp_show.add_argument("step_id")
    sp_show.add_argument("--with-payloads", action="store_true")
    sp_show.add_argument("--run", default=None)
    sp_show.add_argument("--store-dir", default=None)

    sp_output = step_sub.add_parser("output", help="Show a step output node")
    sp_output.add_argument("step_id")
    sp_output.add_argument("--run", default=None)
    sp_output.add_argument("--store-dir", default=None)

    sp_inputs = step_sub.add_parser("inputs", help="Show step input nodes")
    sp_inputs.add_argument("step_id")
    sp_inputs.add_argument("--run", default=None)
    sp_inputs.add_argument("--store-dir", default=None)

    sp_payloads = step_sub.add_parser("payloads", help="Show step payloads")
    sp_payloads.add_argument("step_id")
    sp_payloads.add_argument("--run", default=None)
    sp_payloads.add_argument("--store-dir", default=None)
    return parser


def run_step_command(
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
    payload = StepPayload(
        payload_id="pending",
        target_id="pending",
        type=payload_type,
        content=content,
    )
    before = graph_counts(handle)
    step = handle.add_step(
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
    return {"step": step.to_dict()}


def run_step_create_command(
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
        target_kind="step",
        target_id="pending",
        payload_id="pending",
        json_data=json_data,
        field_data=field_data,
    )
    before = graph_counts(handle)
    step = handle.add_step(
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
    return {"step": step.to_dict()}


def cli_step(args) -> int:
    try:
        if args.step_command == "create":
            result = run_step_create_command(
                run_id=resolve_run_id_from_args(args),
                input_node_ids=args.input_nodes,
                payload_type=args.payload_type,
                field_data=parse_field_args(args.field),
                json_data=parse_json_object(args.json),
                store_dir=args.store_dir,
                user_id=resolve_user_id_from_args(args),
                work_session_id=resolve_work_session_id_from_args(args),
            )
            print(json.dumps(result["step"], ensure_ascii=False, indent=2))
            return 0
        if args.step_command == "show":
            result = run_show_command(
                run_id=resolve_run_id_from_args(args),
                node_id=None,
                step_id=args.step_id,
                payload_id=None,
                with_payloads=args.with_payloads,
                outputs=True,
                store_dir=args.store_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.step_command == "output":
            result = run_outcomes_command(
                run_id=resolve_run_id_from_args(args),
                step_id=args.step_id,
                include_payloads=False,
                store_dir=args.store_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.step_command == "inputs":
            result = run_show_command(
                run_id=resolve_run_id_from_args(args),
                node_id=None,
                step_id=args.step_id,
                payload_id=None,
                with_payloads=False,
                outputs=False,
                store_dir=args.store_dir,
            )
            print(json.dumps({"input_node_ids": result["input_node_ids"]}, ensure_ascii=False, indent=2))
            return 0
        if args.step_command == "payloads":
            result = run_show_command(
                run_id=resolve_run_id_from_args(args),
                node_id=None,
                step_id=args.step_id,
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
