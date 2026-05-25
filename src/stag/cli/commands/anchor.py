"""stag CLI anchor command."""

from __future__ import annotations

import argparse
import json

from stag.cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)
from stag.cli.append_batch import graph_counts, maybe_append_or_save


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "anchor",
        help="Create a scope anchor node from an existing node",
        description=(
            "Create a lightweight branching anchor using a scope_refinement plan "
            "and a completed result."
        ),
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--from", required=True, dest="from_node_id", metavar="NODE_ID")
    parser.add_argument("--label", required=True)
    parser.add_argument("--store-dir", default=".stag/runs")
    parser.add_argument("--user", default=None)
    parser.add_argument("--work-session", default=None)
    return parser


def run_anchor_command(
    *,
    run_id: str,
    from_node_id: str,
    label: str,
    store_dir: str,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    before = graph_counts(handle)
    node = handle.anchor(
        from_node_id,
        label,
        user_id=user_id,
        work_session_id=work_session_id,
    )
    transition_id = handle.run_graph.transitions_to_node(node.node_id)[0]
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=work_session_id,
        before=before,
    )
    return {
        "anchor": {
            "transition_id": transition_id,
            "node_id": node.node_id,
            "label": label,
        }
    }


def cli_anchor(args) -> int:
    result = run_anchor_command(
        run_id=resolve_run_id_from_args(args),
        from_node_id=args.from_node_id,
        label=args.label,
        store_dir=args.store_dir,
        user_id=resolve_user_id_from_args(args),
        work_session_id=resolve_work_session_id_from_args(args),
    )
    print(json.dumps(result["anchor"], ensure_ascii=False, indent=2))
    return 0
