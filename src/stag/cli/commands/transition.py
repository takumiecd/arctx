"""stag CLI transition command."""

from __future__ import annotations

import argparse
import json
import sys

from stag.cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)
from stag.cli.append_batch import graph_counts, maybe_append_or_save
from stag.core.schema.payloads import TransitionPayload


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "transition",
        help="Create a Transition from one or more nodes",
    )
    parser.add_argument("--run", default=None)
    parser.add_argument(
        "--inputs",
        action="append",
        required=True,
        dest="input_nodes",
        metavar="NODE_ID",
        help="Input node (repeatable for multi-node transitions)",
    )
    parser.add_argument("--type", required=True, dest="payload_type", metavar="TYPE",
                        help="Payload type string (free-form, e.g. 'experiment', 'suggestion')")
    parser.add_argument("--content", default="{}", metavar="JSON",
                        help="JSON object for payload content (default: {})")
    parser.add_argument("--max-outcomes", type=int, default=1, dest="max_outcomes",
                        help="Number of sibling transitions to create (default: 1)")
    parser.add_argument("--store-dir", default=".stag/runs")
    parser.add_argument("--user", default=None)
    parser.add_argument("--work-session", default=None)
    return parser


def run_transition_command(
    *,
    run_id: str,
    input_node_ids: list[str],
    payload_type: str,
    content: dict,
    max_outcomes: int = 1,
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
    transitions = handle.transition(
        input_node_ids,
        payload,
        max_outcomes=max_outcomes,
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
    return {"transitions": [t.to_dict() for t in transitions]}


def cli_transition(args) -> int:
    try:
        content = json.loads(args.content)
    except json.JSONDecodeError as exc:
        print(f"error: --content is not valid JSON: {exc}", file=sys.stderr)
        return 1
    try:
        result = run_transition_command(
            run_id=resolve_run_id_from_args(args),
            input_node_ids=args.input_nodes,
            payload_type=args.payload_type,
            content=content,
            max_outcomes=args.max_outcomes,
            store_dir=args.store_dir,
            user_id=resolve_user_id_from_args(args),
            work_session_id=resolve_work_session_id_from_args(args),
        )
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result["transitions"], ensure_ascii=False, indent=2))
    return 0
