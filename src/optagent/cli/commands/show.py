"""optagent CLI show command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("show", help="Show run details")
    parser.add_argument("--run", default=None)
    parser.add_argument("--node", dest="node_id", default=None)
    parser.add_argument("--input-transition", dest="input_transition_id", default=None)
    parser.add_argument("--output-transition", dest="output_transition_id", default=None)
    parser.add_argument("--payload", dest="payload_id", default=None)
    parser.add_argument("--with-payloads", action="store_true")
    parser.add_argument("--outputs", action="store_true",
                       help="(with --input-transition) include output transitions")
    parser.add_argument("--store-dir", default=".optagent/runs")
    return parser


def run_show_command(
    *,
    run_id: str,
    node_id: str | None,
    input_transition_id: str | None,
    output_transition_id: str | None,
    payload_id: str | None,
    with_payloads: bool,
    outputs: bool,
    store_dir: str,
) -> dict:
    if outputs and input_transition_id is None:
        raise ValueError("--outputs can only be used with --input-transition")
    if with_payloads and payload_id is not None:
        raise ValueError("--with-payloads cannot be used with --payload")

    store = JsonlRunStore(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    g = handle.run_graph

    if node_id is not None:
        node = g.nodes.get(node_id)
        if node is None:
            raise KeyError(f"unknown node_id: {node_id}")
        result: dict = {"node": node.to_dict()}
        if with_payloads:
            result["payloads"] = [
                p.to_dict() for p in g.payloads_for_node(node_id)
            ]
        return result

    if input_transition_id is not None:
        it = g.input_transitions.get(input_transition_id)
        if it is None:
            raise KeyError(f"unknown input_transition_id: {input_transition_id}")
        result = {"input_transition": it.to_dict()}
        if with_payloads:
            result["payloads"] = [
                p.to_dict()
                for p in g.payloads_for_input_transition(input_transition_id)
            ]
        if outputs:
            ot_ids = g.output_transitions_from_it.get(input_transition_id, [])
            result["outputs"] = [
                _format_output_ref(g, ot_id, with_payloads) for ot_id in ot_ids
            ]
        return result

    if output_transition_id is not None:
        ot = g.output_transitions.get(output_transition_id)
        if ot is None:
            raise KeyError(f"unknown output_transition_id: {output_transition_id}")
        result = {"output_transition": ot.to_dict()}
        if with_payloads:
            result["payloads"] = [
                p.to_dict()
                for p in g.payloads_for_output_transition(output_transition_id)
            ]
        return result

    if payload_id is not None:
        payload = g.payloads.get(payload_id)
        if payload is None:
            raise KeyError(f"unknown payload_id: {payload_id}")
        return {"payload": payload.to_dict()}

    return {
        "run_id": handle.run_id,
        "requirement_id": handle.requirement.requirement_id,
        "root_node_id": handle.root_node_id,
        "node_count": len(g.nodes),
        "input_transition_count": len(g.input_transitions),
        "output_transition_count": len(g.output_transitions),
        "payload_count": len(g.payloads),
        "views": [v.name for v in handle.run_graph.views.values()],
    }


def _format_output_ref(g, ot_id: str, include_payloads: bool) -> dict:
    ot = g.output_transitions.get(ot_id)
    entry: dict = {
        "output_transition": ot.to_dict() if ot else None,
        "kind": g.output_kind(ot_id),
    }
    if include_payloads:
        entry["payloads"] = [
            p.to_dict() for p in g.payloads_for_output_transition(ot_id)
        ]
    return entry


def cli_show(args) -> int:
    result = run_show_command(
        run_id=resolve_run_id_from_args(args),
        node_id=args.node_id,
        input_transition_id=args.input_transition_id,
        output_transition_id=args.output_transition_id,
        payload_id=args.payload_id,
        with_payloads=args.with_payloads,
        outputs=args.outputs,
        store_dir=args.store_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
