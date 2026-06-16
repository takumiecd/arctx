"""arctx CLI gate-type PR: ``propose`` / ``accept`` / ``reject``.

A PR is an append-only review STATE in the DAG, decoupled from transport:

- ``propose SOURCE --into TARGET`` attaches a ``proposal`` payload to SOURCE
  (pending). The target's tip is NOT advanced yet — that is what "pending" means.
- ``accept SOURCE`` does a GUARDED merge: a multi-input ``add_step`` joining
  SOURCE into the proposal's TARGET. The join runs arctx's existing invariants
  (target active / not cut, no cycle); if the base was cut or the target advanced
  since the proposal, accept is REFUSED with a reason → rebase and re-propose.
  arctx never silently corrupts the graph.
- ``reject SOURCE --reason ...`` is a ``cut`` (kept in the DAG, inactive).

No new core concept: ``proposal`` is a generic node payload, accept delegates to
``add_step``, reject delegates to ``cut``. Status is derived (open = proposal
present, source not cut, target not yet merged).
"""

from __future__ import annotations

import argparse
import json
import sys

from arctx.core.cuts import inactive_node_ids

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)
from arctx_cli.payload_builder import build_payload


def _load(run_id, store_dir):
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    return store, store.load_run(run_id)


def _node_payload(handle, target_id, fields):
    return build_payload(
        payload_type="node_payload", target_kind="node",
        target_id=target_id, payload_id=handle._next_id("pl"),
        json_data={}, field_data=fields,
    )


def _find_proposal(graph, node_id):
    if node_id not in graph.nodes:
        raise KeyError(f"unknown node: {node_id}")
    for p in graph.payloads_for_node(node_id):
        if getattr(p, "type", None) == "proposal":
            return p
    raise ValueError(f"no proposal on node {node_id}; run `arctx propose` first")


def _status(graph, node_id, inactive):
    if node_id in inactive:
        return "rejected"
    for p in graph.payloads_for_node(node_id):
        if getattr(p, "type", None) == "proposal_resolution" \
                and p.content.get("status") == "accepted":
            return "accepted"
    return "open"


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def run_propose_command(*, run_id, source_node, target_node, title, store_dir,
                        user_id=None, work_session_id=None):
    """Open a pending proposal: SOURCE proposed to merge into TARGET."""
    store, handle = _load(run_id, store_dir)
    g = handle.run_graph
    inactive = inactive_node_ids(g)
    for nid, role in ((source_node, "source"), (target_node, "target")):
        if nid not in g.nodes:
            raise KeyError(f"unknown {role} node: {nid}")
        if nid in inactive:
            raise ValueError(f"{role} node {nid} is cut")
    before = graph_counts(handle)
    payload = _node_payload(handle, source_node, {
        "type": "proposal",
        "target": target_node,
        "status": "open",
        "title": title or f"propose {source_node} -> {target_node}",
    })
    handle.attach(source_node, payload, user_id=user_id, work_session_id=work_session_id)
    maybe_append_or_save(store=store, handle=handle, user_id=user_id,
                         work_session_id=work_session_id, before=before)
    return {"proposal": source_node, "target": target_node, "status": "open"}


def run_accept_command(*, run_id, source_node, title, store_dir,
                       user_id=None, work_session_id=None):
    """Accept a proposal by a GUARDED merge into its target (or refuse)."""
    store, handle = _load(run_id, store_dir)
    g = handle.run_graph
    prop = _find_proposal(g, source_node)
    target_node = prop.content.get("target")

    # Stale check: if the target was extended since the proposal, main moved.
    if g.steps_from_node(target_node):
        raise ValueError(
            f"target {target_node} has advanced since the proposal; rebase your "
            "lane onto the current tip and re-propose"
        )

    before = graph_counts(handle)
    merge = build_payload(
        payload_type="step_payload", target_kind="step",
        target_id="pending", payload_id="pending", json_data={},
        field_data={"type": "merge",
                    "title": title or f"accept: merge {source_node} into {target_node}"},
    )
    try:
        step = handle.add_step([source_node, target_node], merge,
                               user_id=user_id, work_session_id=work_session_id)
    except (ValueError, KeyError) as exc:
        # arctx's own invariant (cut base / cycle / missing dep) refused the merge.
        raise ValueError(
            f"accept refused — graph consistency: {exc}. "
            "rebase onto the current target and re-propose"
        ) from exc

    handle.attach(source_node, _node_payload(handle, source_node, {
        "type": "proposal_resolution", "status": "accepted",
        "merged": step.output_node_id,
    }), user_id=user_id, work_session_id=work_session_id)
    maybe_append_or_save(store=store, handle=handle, user_id=user_id,
                         work_session_id=work_session_id, before=before)
    return {"accepted": source_node, "merged_node": step.output_node_id,
            "step": step.step_id}


def run_reject_command(*, run_id, source_node, reason, store_dir,
                       user_id=None, work_session_id=None):
    """Reject a proposal = cut SOURCE with a reason (kept in the DAG)."""
    store, handle = _load(run_id, store_dir)
    _find_proposal(handle.run_graph, source_node)
    before = graph_counts(handle)
    handle.cut(source_node, target_kind="node", reason=reason,
               user_id=user_id, work_session_id=work_session_id)
    maybe_append_or_save(store=store, handle=handle, user_id=user_id,
                         work_session_id=work_session_id, before=before)
    return {"rejected": source_node, "reason": reason}


def list_proposals(*, run_id, store_dir):
    """List all proposals with derived status (open = the PR inbox)."""
    _, handle = _load(run_id, store_dir)
    g = handle.run_graph
    inactive = inactive_node_ids(g)
    out = []
    for node_id in g.nodes:
        for p in g.payloads_for_node(node_id):
            if getattr(p, "type", None) == "proposal":
                out.append({
                    "source": node_id,
                    "target": p.content.get("target"),
                    "status": _status(g, node_id, inactive),
                })
                break
    return out


# ---------------------------------------------------------------------------
# parsers / dispatch
# ---------------------------------------------------------------------------


def add_propose_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``propose`` command."""
    p = subparsers.add_parser(
        "propose", help="Propose merging a node into a target (opens a pending PR)")
    p.add_argument("source", nargs="?", help="Source tip node to propose")
    p.add_argument("--into", dest="target", default=None, help="Target node to merge into")
    p.add_argument("--title", default=None)
    p.add_argument("--list", action="store_true", dest="list_proposals",
                   help="List proposals (open = pending review)")
    p.add_argument("--run", default=None)
    p.add_argument("--store-dir", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--work-session", default=None)
    return p


def add_accept_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``accept`` command."""
    p = subparsers.add_parser(
        "accept", help="Accept a proposal (guarded merge into its target)")
    p.add_argument("source", help="Source node of the proposal to accept")
    p.add_argument("--title", default=None)
    p.add_argument("--run", default=None)
    p.add_argument("--store-dir", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--work-session", default=None)
    return p


def add_reject_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``reject`` command."""
    p = subparsers.add_parser(
        "reject", help="Reject a proposal (cut + reason, kept in the DAG)")
    p.add_argument("source", help="Source node of the proposal to reject")
    p.add_argument("--reason", default=None)
    p.add_argument("--run", default=None)
    p.add_argument("--store-dir", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--work-session", default=None)
    return p


def cli_propose(args) -> int:
    """Dispatch ``propose`` (or --list)."""
    try:
        if args.list_proposals:
            proposals = list_proposals(run_id=resolve_run_id_from_args(args),
                                       store_dir=args.store_dir)
            print(json.dumps({"proposals": proposals}, ensure_ascii=False, indent=2))
            return 0
        if not args.source or not args.target:
            raise ValueError("usage: arctx propose SOURCE --into TARGET")
        result = run_propose_command(
            run_id=resolve_run_id_from_args(args),
            source_node=args.source, target_node=args.target, title=args.title,
            store_dir=args.store_dir, user_id=resolve_user_id_from_args(args),
            work_session_id=resolve_work_session_id_from_args(args),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def cli_accept(args) -> int:
    """Dispatch ``accept``."""
    try:
        result = run_accept_command(
            run_id=resolve_run_id_from_args(args), source_node=args.source,
            title=args.title, store_dir=args.store_dir,
            user_id=resolve_user_id_from_args(args),
            work_session_id=resolve_work_session_id_from_args(args),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def cli_reject(args) -> int:
    """Dispatch ``reject``."""
    try:
        result = run_reject_command(
            run_id=resolve_run_id_from_args(args), source_node=args.source,
            reason=args.reason, store_dir=args.store_dir,
            user_id=resolve_user_id_from_args(args),
            work_session_id=resolve_work_session_id_from_args(args),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
