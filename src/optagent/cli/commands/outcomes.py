"""optagent CLI outcomes command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "outcomes", help="List predictions/observations for an InputTransition"
    )
    parser.add_argument("input_transition_id", help="InputTransition to inspect")
    parser.add_argument("--run", default=None)
    parser.add_argument("--include-payloads", action="store_true")
    parser.add_argument("--store-dir", default=".optagent/runs")
    return parser


def run_outcomes_command(
    *,
    run_id: str,
    input_transition_id: str,
    include_payloads: bool,
    store_dir: str,
) -> dict:
    store = JsonlRunStore(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    g = handle.run_graph

    result = handle.outcomes(input_transition_id)

    if include_payloads:
        result["predictions"] = [
            {
                "output_transition_id": ot_id,
                "payloads": [
                    p.to_dict() for p in g.payloads_for_output_transition(ot_id)
                ],
            }
            for ot_id in result["predictions"]
        ]
        result["observations"] = [
            {
                "output_transition_id": ot_id,
                "payloads": [
                    p.to_dict() for p in g.payloads_for_output_transition(ot_id)
                ],
            }
            for ot_id in result["observations"]
        ]
        result["active_observations"] = [
            {
                "output_transition_id": ot_id,
                "payloads": [
                    p.to_dict() for p in g.payloads_for_output_transition(ot_id)
                ],
            }
            for ot_id in result["active_observations"]
        ]
        result["inactive_observations"] = [
            {
                "output_transition_id": ot_id,
                "payloads": [
                    p.to_dict() for p in g.payloads_for_output_transition(ot_id)
                ],
            }
            for ot_id in result["inactive_observations"]
        ]

    return result


def cli_outcomes(args) -> int:
    result = run_outcomes_command(
        run_id=resolve_run_id_from_args(args),
        input_transition_id=args.input_transition_id,
        include_payloads=args.include_payloads,
        store_dir=args.store_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
