"""File-backed shared DAG sync prototype.

This module treats ``.stag/remotes/<remote>/runs/<shared_run>/records.jsonl``
as a local stand-in for a shared append log. It is intentionally small and
single-machine oriented; the goal is to exercise the sync contract before
introducing HTTP or database backends.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stag.core import _json as _fast_json
from stag.core.graph_view import GraphView
from stag.core.run import RunHandle
from stag.core.run_graph import RunGraph
from stag.core.schema.graph import InputTransition, Node, OutputTransition
from stag.core.schema.payloads import payload_from_dict


RecordTuple = tuple[str, str, dict[str, Any]]


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
    path = _records_path(remote_dir, remote, shared_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
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
    remote_records = _flatten_batches(_read_batches(remote_dir, remote, shared_run_id))
    remote_keys = {_body_key(r["record_kind"], r["body"]) for r in remote_records}
    local_keys = {_body_key(kind, body) for kind, _, body in local_records}
    return {
        "run_id": handle.run_id,
        "remote": remote,
        "shared_run_id": shared_run_id,
        "local_records": len(local_records),
        "remote_records": len(remote_records),
        "unpushed_records": sum(
            1 for kind, _, body in local_records if _body_key(kind, body) not in remote_keys
        ),
        "unpulled_records": sum(
            1 for record in remote_records
            if _body_key(record["record_kind"], record["body"]) not in local_keys
        ),
        "records_path": str(_records_path(remote_dir, remote, shared_run_id)),
    }


def sync_push(
    *,
    handle: RunHandle,
    run_path: Path,
    remote: str,
    shared_run_id: str,
    remote_dir: str | Path,
    workspace_id: str,
    actor_id: str,
    actor_type: str = "human",
) -> dict[str, Any]:
    """Append local records missing from the file-backed shared run."""
    path = _records_path(remote_dir, remote, shared_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    remote_batches = _read_batches(remote_dir, remote, shared_run_id)
    remote_records = _flatten_batches(remote_batches)
    remote_by_key = {
        _body_key(r["record_kind"], r["body"]): r
        for r in remote_records
    }
    idmap = _read_idmap(run_path=run_path, remote=remote, shared_run_id=shared_run_id)

    next_seq = len(remote_batches) + 1
    pushed_batches: list[dict[str, Any]] = []
    new_mappings: list[dict[str, str]] = []
    for batch in _local_batches(handle):
        missing_records: list[dict[str, Any]] = []
        for kind, local_id, body in batch["records"]:
            key = _body_key(kind, body)
            existing = remote_by_key.get(key)
            map_key = _idmap_key(remote, shared_run_id, kind, local_id)
            if existing is not None:
                if existing["body"] != body:
                    raise RuntimeError(f"remote already has different body for {kind}:{local_id}")
                if map_key not in idmap:
                    new_mappings.append(
                        _idmap_row(remote, shared_run_id, kind, local_id, existing["shared_id"])
                    )
                    idmap[map_key] = existing["shared_id"]
                continue

            shared_id = idmap.get(map_key) or _new_shared_id(kind)
            missing_records.append(
                {
                    "record_kind": kind,
                    "local_id": local_id,
                    "shared_id": shared_id,
                    "body": body,
                }
            )
            new_mappings.append(_idmap_row(remote, shared_run_id, kind, local_id, shared_id))
            idmap[map_key] = shared_id

        if not missing_records:
            continue

        envelope = {
            "seq": next_seq,
            "batch_id": _new_shared_id("batch"),
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
            remote_by_key[_body_key(record["record_kind"], record["body"])] = record
        next_seq += 1

    if pushed_batches:
        with path.open("a", encoding="utf-8") as fh:
            for batch in pushed_batches:
                fh.write(_fast_json.dumps(batch) + "\n")
    if new_mappings:
        _append_idmap(
            run_path=run_path,
            rows=new_mappings,
        )

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
    run_path: Path,
    remote: str,
    shared_run_id: str,
    remote_dir: str | Path,
) -> dict[str, Any]:
    """Apply records missing from the shared run into the local graph."""
    batches = _read_batches(remote_dir, remote, shared_run_id)
    pulled = 0
    new_mappings: list[dict[str, str]] = []
    for record in _flatten_batches(batches):
        if _apply_record(handle.run_graph, record["record_kind"], record["body"]):
            pulled += 1
        local_id = _local_id_for_body(record["record_kind"], record["body"])
        new_mappings.append(
            _idmap_row(
                remote,
                shared_run_id,
                record["record_kind"],
                local_id,
                record["shared_id"],
            )
        )
    _refresh_counters(handle)
    _append_idmap(run_path=run_path, rows=new_mappings)
    return {
        "run_id": handle.run_id,
        "remote": remote,
        "shared_run_id": shared_run_id,
        "pulled_batches": len(batches),
        "pulled_records": pulled,
        "records_path": str(_records_path(remote_dir, remote, shared_run_id)),
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
    return [
        record
        for batch in _local_batches(handle)
        for record in batch["records"]
    ]


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

    for it in graph.input_transitions.values():
        records: list[RecordTuple] = [
            ("input_transition", it.input_transition_id, it.to_dict())
        ]
        included.add(("input_transition", it.input_transition_id))
        for payload in graph.payloads_for_input_transition(it.input_transition_id):
            records.append(("payload", payload.payload_id, payload.to_dict()))
            included.add(("payload", payload.payload_id))
        for ot_id in graph.output_transitions_from_it.get(it.input_transition_id, []):
            ot = graph.output_transitions[ot_id]
            to_node = graph.nodes[ot.to_node_id]
            records.append(("node", to_node.node_id, to_node.to_dict()))
            included.add(("node", to_node.node_id))
            records.append(("output_transition", ot.output_transition_id, ot.to_dict()))
            included.add(("output_transition", ot.output_transition_id))
            for payload in graph.payloads_for_output_transition(ot.output_transition_id):
                records.append(("payload", payload.payload_id, payload.to_dict()))
                included.add(("payload", payload.payload_id))
        batches.append(
            {
                "operation": _operation_for_input_transition(graph, it.input_transition_id),
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


def _operation_for_input_transition(graph: RunGraph, it_id: str) -> str:
    payloads = graph.payloads_for_input_transition(it_id)
    if any(getattr(p, "metadata", {}).get("kind") == "anchor" for p in payloads):
        return "anchor"
    for ot_id in graph.output_transitions_from_it.get(it_id, []):
        if any(
            getattr(p, "metadata", {}).get("kind") == "anchor"
            for p in graph.payloads_for_output_transition(ot_id)
        ):
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

    if kind == "input_transition":
        it = InputTransition(
            input_transition_id=str(body["input_transition_id"]),
            input_node_ids=tuple(str(n) for n in (body.get("input_node_ids") or [])),
            metadata=dict(body.get("metadata") or {}),
        )
        existing = graph.input_transitions.get(it.input_transition_id)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, it.input_transition_id)
            return False
        graph.add_input_transition(it)
        return True

    if kind == "output_transition":
        ot = OutputTransition(
            output_transition_id=str(body["output_transition_id"]),
            input_transition_id=str(body["input_transition_id"]),
            to_node_id=str(body["to_node_id"]),
            metadata=dict(body.get("metadata") or {}),
        )
        existing = graph.output_transitions.get(ot.output_transition_id)
        if existing is not None:
            _ensure_same(existing.to_dict(), body, kind, ot.output_transition_id)
            return False
        graph.add_output_transition(ot)
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
        return True

    raise ValueError(f"unknown sync record kind: {kind!r}")


def _refresh_counters(handle: RunHandle) -> None:
    handle._counters["n"] = _max_suffix(handle.run_graph.nodes)
    handle._counters["it"] = _max_suffix(handle.run_graph.input_transitions)
    handle._counters["ot"] = _max_suffix(handle.run_graph.output_transitions)
    handle._counters["pl"] = _max_suffix(handle.run_graph.payloads)


def _max_suffix(ids: dict[str, object]) -> int:
    max_seen = 0
    for item_id in ids:
        _, _, suffix = item_id.rpartition("_")
        if suffix.isdigit():
            max_seen = max(max_seen, int(suffix))
    return max_seen


def _ensure_same(existing: dict[str, Any], incoming: dict[str, Any], kind: str, item_id: str) -> None:
    if existing != incoming:
        raise RuntimeError(f"local {kind}:{item_id} differs from remote record")


def _read_batches(remote_dir: str | Path, remote: str, shared_run_id: str) -> list[dict[str, Any]]:
    path = _records_path(remote_dir, remote, shared_run_id)
    if not path.exists():
        return []
    batches = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = _fast_json.loads(line)
        if "records" in item:
            batches.append(item)
        else:
            batches.append(
                {
                    "seq": item["seq"],
                    "batch_id": item.get("batch_id") or _new_shared_id("batch"),
                    "operation": item.get("record_kind", "record"),
                    "records": [
                        {
                            "record_kind": item["record_kind"],
                            "local_id": _local_id_for_body(item["record_kind"], item["body"]),
                            "shared_id": item.get("shared_id") or _new_shared_id(item["record_kind"]),
                            "body": item["body"],
                        }
                    ],
                    "actor": item.get("actor", {}),
                    "origin": item.get("origin", {}),
                    "created_at": item.get("created_at"),
                }
            )
    return batches


def _flatten_batches(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "record_kind": record["record_kind"],
            "local_id": record.get("local_id"),
            "shared_id": record["shared_id"],
            "body": record["body"],
        }
        for batch in batches
        for record in batch["records"]
    ]


def _records_path(remote_dir: str | Path, remote: str, shared_run_id: str) -> Path:
    return Path(remote_dir) / remote / "runs" / shared_run_id / "records.jsonl"


def _body_key(kind: str, body: dict[str, Any]) -> tuple[str, str]:
    if kind == "node":
        return kind, str(body["node_id"])
    if kind == "input_transition":
        return kind, str(body["input_transition_id"])
    if kind == "output_transition":
        return kind, str(body["output_transition_id"])
    if kind == "payload":
        return kind, str(body["payload_id"])
    if kind == "view":
        return kind, str(body["view_id"])
    raise ValueError(f"unknown sync record kind: {kind!r}")


def _local_id_for_body(kind: str, body: dict[str, Any]) -> str:
    return _body_key(kind, body)[1]


def _idmap_key(remote: str, shared_run_id: str, kind: str, local_id: str) -> tuple[str, str, str, str]:
    return remote, shared_run_id, kind, local_id


def _idmap_row(
    remote: str,
    shared_run_id: str,
    kind: str,
    local_id: str,
    shared_id: str,
) -> dict[str, str]:
    return {
        "remote": remote,
        "shared_run_id": shared_run_id,
        "record_kind": kind,
        "local_id": local_id,
        "shared_id": shared_id,
    }


def _read_idmap(
    *,
    run_path: Path,
    remote: str,
    shared_run_id: str,
) -> dict[tuple[str, str, str, str], str]:
    path = run_path / "idmap.jsonl"
    if not path.exists():
        return {}
    result: dict[tuple[str, str, str, str], str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = _fast_json.loads(line)
        if row.get("remote") != remote or row.get("shared_run_id") != shared_run_id:
            continue
        key = _idmap_key(
            str(row["remote"]),
            str(row["shared_run_id"]),
            str(row["record_kind"]),
            str(row["local_id"]),
        )
        result[key] = str(row["shared_id"])
    return result


def _append_idmap(*, run_path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    path = run_path / "idmap.jsonl"
    existing: set[tuple[str, str, str, str]] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = _fast_json.loads(line)
            existing.add(
                _idmap_key(
                    str(row["remote"]),
                    str(row["shared_run_id"]),
                    str(row["record_kind"]),
                    str(row["local_id"]),
                )
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            key = _idmap_key(
                row["remote"],
                row["shared_run_id"],
                row["record_kind"],
                row["local_id"],
            )
            if key in existing:
                continue
            fh.write(_fast_json.dumps(row) + "\n")
            existing.add(key)


def _new_shared_id(kind: str) -> str:
    return f"{kind}_{uuid.uuid4().hex}"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
