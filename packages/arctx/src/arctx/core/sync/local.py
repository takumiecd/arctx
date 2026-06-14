"""File-backed shared DAG sync prototype.

This module treats ``.arctx/remotes/<remote>/runs/<shared_run>/records.jsonl``
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

from arctx.core.run import RunHandle
from arctx.core.run_graph import RunGraph
from arctx.core.schema.graph import Node, Step
from arctx.core.schema.payloads import payload_from_dict
from arctx.core.sync.records import (
    RecordTuple,
    body_key,
    flatten_batches,
    new_sync_id,
    records_path,
)
from arctx.core.sync.shared_store import FileSharedRunStore


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
        raise RuntimeError("sync is not initialized for this run")
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
    if seed_records:
        batches.append({"operation": "seed", "records": seed_records})

    for step in graph.steps.values():
        records: list[RecordTuple] = [("step", step.step_id, step.to_dict())]
        included.add(("step", step.step_id))

        # Include input and output nodes.
        for nid in step.input_node_ids:
            if ("node", nid) not in included and nid in graph.nodes:
                node = graph.nodes[nid]
                records.append(("node", node.node_id, node.to_dict()))
                included.add(("node", node.node_id))
        if step.output_node_id and ("node", step.output_node_id) not in included:
            nid = step.output_node_id
            if nid in graph.nodes:
                node = graph.nodes[nid]
                records.append(("node", node.node_id, node.to_dict()))
                included.add(("node", node.node_id))

        for payload in graph.payloads_for_step(step.step_id):
            records.append(("payload", payload.payload_id, payload.to_dict()))
            included.add(("payload", payload.payload_id))
        batches.append(
            {
                "operation": _operation_for_step(graph, step.step_id),
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

    return batches


def _operation_for_step(graph: RunGraph, step_id: str) -> str:
    payloads = graph.payloads_for_step(step_id)
    if any(getattr(p, "type", None) == "anchor" for p in payloads):
        return "anchor"
    return "step"


def _apply_record(graph: RunGraph, kind: str, body: dict[str, Any]) -> bool:
    if kind == "node":
        node = Node(node_id=str(body["node_id"]), metadata=dict(body.get("metadata") or {}))
        existing = graph.nodes.get(node.node_id)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, node.node_id)
            return False
        graph.add_node(node)
        return True

    if kind == "step":
        step = Step(
            step_id=str(body["step_id"]),
            input_node_ids=tuple(body.get("input_node_ids") or []),
            output_node_id=str(body.get("output_node_id") or ""),
            metadata=dict(body.get("metadata") or {}),
        )
        existing = graph.steps.get(step.step_id)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, step.step_id)
            return False
        graph.add_step(step)
        return True

    if kind == "payload":
        payload = payload_from_dict(body)
        existing = graph.payloads.get(payload.payload_id)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, payload.payload_id)
            return False
        graph.attach_payload(payload)
        return True

    # Unknown record kinds are silently skipped for forward compatibility.
    return False


def _refresh_counters(handle: RunHandle) -> None:
    handle._counters["n"] = _max_suffix(handle.run_graph.nodes)
    handle._counters["t"] = _max_suffix(handle.run_graph.steps)
    handle._counters["pl"] = _max_suffix(handle.run_graph.payloads)


def _is_empty_seed_graph(graph: RunGraph) -> bool:
    return (
        len(graph.nodes) == 1
        and not graph.steps
        and not graph.payloads
    )


def _clear_graph(graph: RunGraph) -> None:
    graph.nodes.clear()
    graph.steps.clear()
    graph.payloads.clear()
    graph.payloads_by_node.clear()
    graph.payloads_by_step.clear()
    graph.steps_by_input_node.clear()
    graph.step_by_output_node.clear()
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
