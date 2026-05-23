"""stag CLI anchor command."""

from __future__ import annotations

import argparse
import json

from stag.cli.context import resolve_store, resolve_run_id_from_args, resolve_user_id_from_args


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
    return parser


def run_anchor_command(
    *,
    run_id: str,
    from_node_id: str,
    label: str,
    store_dir: str,
    user_id: str | None = None,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    ot = handle.anchor(from_node_id, label, user_id=user_id)
    it = handle.run_graph.input_transitions[ot.input_transition_id]
    store.save_run(handle)
    return {
        "anchor": {
            "input_transition_id": it.input_transition_id,
            "output_transition_id": ot.output_transition_id,
            "node_id": ot.to_node_id,
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
    )
    print(json.dumps(result["anchor"], ensure_ascii=False, indent=2))
    return 0
