"""stag CLI show command."""

from __future__ import annotations

import argparse
import json

from stag.cli.context import resolve_store, resolve_run_id_from_args


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("show", help="Show run details")
    parser.add_argument("--run", default=None)
    parser.add_argument("--node", dest="node_id", default=None)
    parser.add_argument("--transition", dest="transition_id", default=None)
    parser.add_argument("--payload", dest="payload_id", default=None)
    parser.add_argument("--with-payloads", action="store_true")
    parser.add_argument(
        "--outputs", action="store_true", help="(with --transition) include output nodes"
    )
    parser.add_argument("--store-dir", default=".stag/runs")
    return parser


def run_show_command(
    *,
    run_id: str,
    node_id: str | None,
    transition_id: str | None,
    payload_id: str | None,
    with_payloads: bool,
    outputs: bool,
    store_dir: str,
) -> dict:
    if outputs and transition_id is None:
        raise ValueError("--outputs can only be used with --transition")
    if with_payloads and payload_id is not None:
        raise ValueError("--with-payloads cannot be used with --payload")

    store = resolve_store(store_dir)
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
            result["payloads"] = [p.to_dict() for p in g.payloads_for_node(node_id)]
        return result

    if transition_id is not None:
        transition = g.transitions.get(transition_id)
        if transition is None:
            raise KeyError(f"unknown transition_id: {transition_id}")
        result = {
            "transition": transition.to_dict(),
            "input_node_ids": g.transition_inputs(transition_id),
        }
        if with_payloads:
            result["payloads"] = [p.to_dict() for p in g.payloads_for_transition(transition_id)]
        if outputs:
            result["output_nodes"] = [
                g.nodes[node_id].to_dict() for node_id in g.transition_outputs(transition_id)
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
        "transition_count": len(g.transitions),
        "edge_count": len(g.edges),
        "payload_count": len(g.payloads),
        "views": [v.name for v in handle.run_graph.views.values()],
    }


def cli_show(args) -> int:
    result = run_show_command(
        run_id=resolve_run_id_from_args(args),
        node_id=args.node_id,
        transition_id=args.transition_id,
        payload_id=args.payload_id,
        with_payloads=args.with_payloads,
        outputs=args.outputs,
        store_dir=args.store_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
