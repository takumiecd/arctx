"""stag CLI outcomes command."""

from __future__ import annotations

import argparse
import json

from stag.cli.context import resolve_store, resolve_run_id_from_args


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("outcomes", help="List output nodes for a Transition")
    parser.add_argument("transition_id", help="Transition to inspect")
    parser.add_argument("--run", default=None)
    parser.add_argument("--include-payloads", action="store_true")
    parser.add_argument("--store-dir", default=".stag/runs")
    return parser


def run_outcomes_command(
    *,
    run_id: str,
    transition_id: str,
    include_payloads: bool,
    store_dir: str,
) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    g = handle.run_graph

    result = handle.outcomes(transition_id)

    if include_payloads:
        result["transition_payloads"] = [
            p.to_dict() for p in g.payloads_for_transition(transition_id)
        ]
        result["output_nodes"] = [
            {
                "node": g.nodes[node_id].to_dict(),
                "payloads": [p.to_dict() for p in g.payloads_for_node(node_id)],
            }
            for node_id in result["output_node_ids"]
        ]

    return result


def cli_outcomes(args) -> int:
    result = run_outcomes_command(
        run_id=resolve_run_id_from_args(args),
        transition_id=args.transition_id,
        include_payloads=args.include_payloads,
        store_dir=args.store_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
