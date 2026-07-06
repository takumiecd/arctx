"""User-facing arctx add commands."""

from __future__ import annotations

import argparse
import json
import sys

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.commands._lane_context import (
    describe_frontier_candidates,
    resolve_lane_frontiers,
    root_frontier_fallback,
)
from arctx_cli.commands._targets import step_view
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_lane_id_from_args,
)
from arctx_cli.lane_gate import ensure_lane_open
from arctx_cli.payload_builder import build_payload, parse_field_args, parse_json_object


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("add", help="Add a Step from input Nodes")
    parser.add_argument(
        "--from",
        action="append",
        required=False,
        default=None,
        dest="input_nodes",
        metavar="NODE_ID",
        help=(
            "Input node (repeatable for multi-input steps). If omitted, "
            "defaults to the current lane's single active frontier node."
        ),
    )
    parser.add_argument("--title", default=None)
    parser.add_argument("--type", dest="payload_kind", default=None)
    parser.add_argument("--payload-type", default="step_payload")
    parser.add_argument("--field", action="append", default=None, help="Payload field as key=value")
    parser.add_argument("--json", default=None, help="Payload fields as a JSON object")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--lane", default=None)
    parser.add_argument("--force", action="store_true",
                        help="Write even if the target lane is closed")

    return parser


def _default_input_node_ids(handle, lane_id: str) -> list[str]:
    """Default ``--from`` to the current lane's single active frontier node.

    Raises ``ValueError`` (with a corrective, ready-to-copy command) when the
    lane has zero or more than one active frontier, since there is no single
    unambiguous node to continue from.
    """
    context = resolve_lane_frontiers(handle, lane_id)
    frontiers = context.frontier_node_ids
    lane_label = context.lane_name or context.lane_id

    if len(frontiers) == 1:
        return [frontiers[0]]

    if not frontiers:
        root_node_id = root_frontier_fallback(handle)
        if root_node_id is not None:
            return [root_node_id]
        raise ValueError(
            f"--from is required here: lane {lane_label!r} has no active frontiers. "
            f"Pass --from NODE_ID explicitly. Use `arctx guide --context` or "
            f"`arctx dump` to find a node, e.g.: arctx add --from n_xxx ..."
        )

    candidates = describe_frontier_candidates(handle, frontiers)
    listing = "\n".join(f"  - {line}" for line in candidates)
    example = frontiers[0]
    raise ValueError(
        f"--from is required here: lane {lane_label!r} has {len(frontiers)} active "
        f"frontiers. Pick one:\n{listing}\n"
        f"arctx add --from {example} ..."
    )


def run_add_step_command(
    *,
    run_id: str,
    input_node_ids: list[str] | None,
    title: str | None,
    payload_kind: str | None,
    payload_type: str,
    field_data: dict,
    json_data: dict,
    store_dir: str,
    user_id: str | None = None,
    lane_id: str | None = None,
    force: bool = False,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    ensure_lane_open(handle, lane_id, force=force)
    if not input_node_ids:
        input_node_ids = _default_input_node_ids(handle, lane_id or "default")
    data = dict(json_data or {})
    data.update(field_data or {})
    if title is not None:
        data.setdefault("title", title)
        data.setdefault("text", title)
    if payload_kind is not None:
        data.setdefault("type", payload_kind)
    else:
        data.setdefault("type", "step")

    payload = build_payload(
        payload_type=payload_type,
        target_kind="step",
        target_id="pending",
        payload_id="pending",
        json_data={},
        field_data=data,
    )
    before = graph_counts(handle)
    step = handle.add_step(
        input_node_ids,
        payload,
        user_id=user_id,
        lane_id=lane_id,
    )
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane_id,
        before=before,
    )
    return {"step": step_view(step)}


def cli_add(args) -> int:
    try:
        result = run_add_step_command(
            run_id=resolve_run_id_from_args(args),
            input_node_ids=args.input_nodes,
            title=args.title,
            payload_kind=args.payload_kind,
            payload_type=args.payload_type,
            field_data=parse_field_args(args.field),
            json_data=parse_json_object(args.json),
            store_dir=args.store_dir,
            user_id=resolve_user_id_from_args(args),
            lane_id=resolve_lane_id_from_args(args),
            force=args.force,
        )
        print(json.dumps(result["step"], ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
