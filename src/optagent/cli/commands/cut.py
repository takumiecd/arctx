"""optagent CLI cut command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args, resolve_user_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("cut", help="Cut an InputTransition or OutputTransition")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-transition", dest="input_transition_id", metavar="IT_ID")
    group.add_argument("--output-transition", dest="output_transition_id", metavar="OT_ID")
    parser.add_argument("--run", default=None)
    parser.add_argument("--reason", default=None)
    parser.add_argument("--store-dir", default=".optagent/runs")
    parser.add_argument("--user", default=None)
    return parser


def run_cut_command(
    *,
    run_id: str,
    target_id: str,
    target_kind: str,
    reason: str | None,
    store_dir: str,
    user_id: str | None = None,
) -> dict:
    store = JsonlRunStore(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    cut = handle.cut(
        target_id,
        target_kind=target_kind,  # type: ignore[arg-type]
        reason=reason,
        user_id=user_id,
    )
    store.save_run(handle)
    return {"cut": cut.to_dict()}


def cli_cut(args) -> int:
    if args.input_transition_id is not None:
        target_id = args.input_transition_id
        target_kind = "input_transition"
    else:
        target_id = args.output_transition_id
        target_kind = "output_transition"

    result = run_cut_command(
        run_id=resolve_run_id_from_args(args),
        target_id=target_id,
        target_kind=target_kind,
        reason=args.reason,
        store_dir=args.store_dir,
        user_id=resolve_user_id_from_args(args),
    )
    print(json.dumps(result["cut"], ensure_ascii=False, indent=2))
    return 0
