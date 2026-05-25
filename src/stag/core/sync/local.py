"""File-backed shared DAG sync prototype.

This module treats ``.stag/remotes/<remote>/runs/<shared_run>/records.jsonl``
as a local stand-in for a shared append log. It is intentionally small and
single-machine oriented; the goal is to exercise the sync contract before
introducing HTTP or database backends.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stag.core.graph_view import GraphView
from stag.core.run import RunHandle
from stag.core.run_graph import RunGraph
from stag.core.schema.graph import Edge, Node, Transition
from stag.core.schema.payloads import payload_from_dict
from stag.core.sync.records import (
    RecordTuple,
    body_key,
    flatten_batches,
    new_sync_id,
    records_path,
)
from stag.core.sync.shared_store import FileSharedRunStore


@dataclass(frozen=True)
class SyncConfig:
    """Local sync configuration for one run."""

    remote: str
    shared_run_id: str
    remote_dir: str
    workspace_id: str
    actor_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "remote": self.remote,
            "shared_run_id": self.shared_run_id,
            "remote_dir": self.remote_dir,
            "workspace_id": self.workspace_id,
            "actor_id": self.actor_id,
        }


def sync_init(
    *,
    handle: RunHandle,
    run_path: Path,
    remote: str,
    shared_run_id: str,
    remote_dir: str | Path,
    workspace_id: str,
    actor_id: str,
) -> dict[str, Any]:
    """Persist sync config and create the local shared run directory."""
    cfg = SyncConfig(
        remote=remote,
        shared_run_id=shared_run_id,
        remote_dir=str(remote_dir),
        workspace_id=workspace_id,
        actor_id=actor_id,
    )
    run_path.mkdir(parents=True, exist_ok=True)
    _write_json(run_path / "sync.json", cfg.to_dict())
    path = FileSharedRunStore(remote_dir).ensure_run(remote, shared_run_id)
    return {
        "run_id": handle.run_id,
        "remote": remote,
        "shared_run_id": shared_run_id,
        "records_path": str(path),
    }


def sync_status(
    *,
    handle: RunHandle,
    remote: str,
    shared_run_id: str,
    remote_dir: str | Path,
) -> dict[str, Any]:
    """Return local/remote counts and pending push/pull counts."""
    local_records = _local_records(handle)
    shared_store = FileSharedRunStore(remote_dir)
    remote_records = flatten_batches(shared_store.read_batches(remote, shared_run_id))
    remote_keys = {body_key(r["record_kind"], r["body"]) for r in remote_records}
    local_keys = {body_key(kind, body) for kind, _, body in local_records}
    return {
        "run_id": handle.run_id,
        "remote": remote,
        "shared_run_id": shared_run_id,
        "local_records": len(local_records),
        "remote_records": len(remote_records),
        "unpushed_records": sum(
            1 for kind, _, body in local_records if body_key(kind, body) not in remote_keys
        ),
        "unpulled_records": sum(
            1
            for record in remote_records
            if body_key(record["record_kind"], record["body"]) not in local_keys
        ),
        "records_path": str(records_path(remote_dir, remote, shared_run_id)),
    }


def sync_push(
    *,
    handle: RunHandle,
    remote: str,
    shared_run_id: str,
    remote_dir: str | Path,
    workspace_id: str,
    actor_id: str,
    actor_type: str = "human",
) -> dict[str, Any]:
    """Append local records missing from the file-backed shared run."""
    shared_store = FileSharedRunStore(remote_dir)
    path = shared_store.records_path(remote, shared_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    remote_batches = shared_store.read_batches(remote, shared_run_id)
    remote_records = flatten_batches(remote_batches)
    remote_by_key = {body_key(r["record_kind"], r["body"]): r for r in remote_records}

    next_seq = len(remote_batches) + 1
    pushed_batches: list[dict[str, Any]] = []
    for batch in _local_batches(handle):
        missing_records: list[dict[str, Any]] = []
        for kind, local_id, body in batch["records"]:
            key = body_key(kind, body)
            existing = remote_by_key.get(key)
            if existing is not None:
                if existing["body"] != body:
                    raise RuntimeError(f"remote already has different body for {kind}:{local_id}")
                continue

            missing_records.append(
                {
                    "record_kind": kind,
                    "record_id": local_id,
                    "body": body,
                }
            )

        if not missing_records:
            continue

        envelope = {
            "seq": next_seq,
            "batch_id": new_sync_id("batch"),
            "operation": batch["operation"],
            "records": missing_records,
            "actor": {
                "actor_id": actor_id,
                "actor_type": actor_type,
            },
            "origin": {
                "workspace_id": workspace_id,
                "local_run_id": handle.run_id,
            },
            "created_at": _now_iso(),
        }
        pushed_batches.append(envelope)
        for record in missing_records:
            remote_by_key[body_key(record["record_kind"], record["body"])] = record
        next_seq += 1

    shared_store.append_batches(remote, shared_run_id, pushed_batches)

    return {
        "run_id": handle.run_id,
        "remote": remote,
        "shared_run_id": shared_run_id,
        "pushed_batches": len(pushed_batches),
        "pushed_records": sum(len(batch["records"]) for batch in pushed_batches),
        "records_path": str(path),
    }


def sync_pull(
    *,
    handle: RunHandle,
    remote: str,
    shared_run_id: str,
    remote_dir: str | Path,
) -> dict[str, Any]:
    """Apply records missing from the shared run into the local graph."""
    shared_store = FileSharedRunStore(remote_dir)
    batches = shared_store.read_batches(remote, shared_run_id)
    if batches and batches[0].get("operation") == "seed" and _is_empty_seed_graph(handle.run_graph):
        _clear_graph(handle.run_graph)
    pulled = 0
    for record in flatten_batches(batches):
        if _apply_record(handle.run_graph, record["record_kind"], record["body"]):
            pulled += 1
    _refresh_counters(handle)
    return {
        "run_id": handle.run_id,
        "remote": remote,
        "shared_run_id": shared_run_id,
        "pulled_batches": len(batches),
        "pulled_records": pulled,
        "records_path": str(records_path(remote_dir, remote, shared_run_id)),
    }


def load_sync_config(run_path: Path) -> dict[str, str]:
    """Load ``sync.json`` for a run."""
    path = run_path / "sync.json"
    if not path.exists():
        raise RuntimeError("sync is not initialized. Use 'stag sync init ...'")
    return json.loads(path.read_text(encoding="utf-8"))


def default_remote_dir(store_dir: str | Path) -> Path:
    """Return the default local remotes root for a store directory."""
    return Path(store_dir).parent / "remotes"


def _local_records(handle: RunHandle) -> list[RecordTuple]:
    return [record for batch in _local_batches(handle) for record in batch["records"]]


def _local_batches(handle: RunHandle) -> list[dict[str, Any]]:
    graph = handle.run_graph
    batches: list[dict[str, Any]] = []
    included: set[tuple[str, str]] = set()

    seed_records: list[RecordTuple] = []
    if handle.root_node_id in graph.nodes:
        node = graph.nodes[handle.root_node_id]
        seed_records.append(("node", node.node_id, node.to_dict()))
        included.add(("node", node.node_id))
    for view in graph.views.values():
        seed_records.append(("view", view.view_id, view.to_dict()))
        included.add(("view", view.view_id))
    if seed_records:
        batches.append({"operation": "seed", "records": seed_records})

    for transition in graph.transitions.values():
        records = [("transition", transition.transition_id, transition.to_dict())]
        included.add(("transition", transition.transition_id))

        for edge_id in graph.incoming_edges.get(f"transition:{transition.transition_id}", []):
            edge = graph.edges[edge_id]
            if edge.from_kind == "node" and edge.from_id in graph.nodes:
                node = graph.nodes[edge.from_id]
                if ("node", node.node_id) not in included:
                    records.append(("node", node.node_id, node.to_dict()))
                    included.add(("node", node.node_id))
            records.append(("edge", edge.edge_id, edge.to_dict()))
            included.add(("edge", edge.edge_id))

        for edge_id in graph.outgoing_edges.get(f"transition:{transition.transition_id}", []):
            edge = graph.edges[edge_id]
            if edge.to_kind == "node" and edge.to_id in graph.nodes:
                node = graph.nodes[edge.to_id]
                if ("node", node.node_id) not in included:
                    records.append(("node", node.node_id, node.to_dict()))
                    included.add(("node", node.node_id))
            records.append(("edge", edge.edge_id, edge.to_dict()))
            included.add(("edge", edge.edge_id))

        for payload in graph.payloads_for_transition(transition.transition_id):
            records.append(("payload", payload.payload_id, payload.to_dict()))
            included.add(("payload", payload.payload_id))
        batches.append(
            {
                "operation": _operation_for_transition(graph, transition.transition_id),
                "records": records,
            }
        )

    for payload in graph.payloads.values():
        key = ("payload", payload.payload_id)
        if key not in included:
            batches.append(
                {
                    "operation": f"{payload.payload_type}_payload",
                    "records": [("payload", payload.payload_id, payload.to_dict())],
                }
            )
            included.add(key)

    for node in graph.nodes.values():
        key = ("node", node.node_id)
        if key not in included:
            batches.append(
                {"operation": "node", "records": [("node", node.node_id, node.to_dict())]}
            )
            included.add(key)

    for edge in graph.edges.values():
        key = ("edge", edge.edge_id)
        if key not in included:
            batches.append(
                {"operation": "edge", "records": [("edge", edge.edge_id, edge.to_dict())]}
            )
            included.add(key)

    return batches


def _operation_for_transition(graph: RunGraph, transition_id: str) -> str:
    payloads = graph.payloads_for_transition(transition_id)
    if any(getattr(p, "metadata", {}).get("kind") == "anchor" for p in payloads):
        return "anchor"
    return "transition"


def _apply_record(graph: RunGraph, kind: str, body: dict[str, Any]) -> bool:
    if kind == "node":
        node = Node(node_id=str(body["node_id"]), metadata=dict(body.get("metadata") or {}))
        existing = graph.nodes.get(node.node_id)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, node.node_id)
            return False
        graph.add_node(node)
        return True

    if kind == "transition":
        transition = Transition(
            transition_id=str(body["transition_id"]),
            metadata=dict(body.get("metadata") or {}),
        )
        existing = graph.transitions.get(transition.transition_id)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, transition.transition_id)
            return False
        graph.add_transition(transition)
        return True

    if kind == "edge":
        edge = Edge(
            edge_id=str(body["edge_id"]),
            from_kind=body["from_kind"],
            from_id=str(body["from_id"]),
            to_kind=body["to_kind"],
            to_id=str(body["to_id"]),
            metadata=dict(body.get("metadata") or {}),
        )
        existing = graph.edges.get(edge.edge_id)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, edge.edge_id)
            return False
        graph.add_edge(edge)
        return True

    if kind == "payload":
        payload = payload_from_dict(body)
        existing = graph.payloads.get(payload.payload_id)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, payload.payload_id)
            return False
        graph.attach_payload(payload)
        return True

    if kind == "view":
        view = GraphView(
            view_id=str(body["view_id"]),
            name=str(body["name"]),
            root_node_id=str(body["root_node_id"]),
            metadata=dict(body.get("metadata") or {}),
        )
        existing = graph.views.get(view.name)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, view.name)
            return False
        graph.add_view(view)
        if view.name == "main":
            graph.metadata["root_node_id"] = view.root_node_id
        return True

    raise ValueError(f"unknown sync record kind: {kind!r}")


def _refresh_counters(handle: RunHandle) -> None:
    handle._counters["n"] = _max_suffix(handle.run_graph.nodes)
    handle._counters["t"] = _max_suffix(handle.run_graph.transitions)
    handle._counters["e"] = _max_suffix(handle.run_graph.edges)
    handle._counters["pl"] = _max_suffix(handle.run_graph.payloads)


def _is_empty_seed_graph(graph: RunGraph) -> bool:
    return (
        len(graph.nodes) == 1
        and not graph.transitions
        and not graph.edges
        and not graph.payloads
        and set(graph.views) <= {"main"}
    )


def _clear_graph(graph: RunGraph) -> None:
    graph.nodes.clear()
    graph.transitions.clear()
    graph.edges.clear()
    graph.payloads.clear()
    graph.views.clear()
    graph.payloads_by_node.clear()
    graph.payloads_by_transition.clear()
    graph.outgoing_edges.clear()
    graph.incoming_edges.clear()
    graph.metadata.pop("root_node_id", None)


def _max_suffix(ids: dict[str, object]) -> int:
    max_seen = 0
    for item_id in ids:
        _, _, suffix = item_id.rpartition("_")
        if suffix.isdigit():
            max_seen = max(max_seen, int(suffix))
    return max_seen


def _ensure_same(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    kind: str,
    item_id: str,
) -> None:
    if existing != incoming:
        raise RuntimeError(f"local {kind}:{item_id} differs from remote record")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
