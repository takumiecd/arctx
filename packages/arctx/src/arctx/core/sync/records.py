"""Shared sync record helpers."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from arctx.core import _json as _fast_json

RecordTuple = tuple[str, str, dict[str, Any]]


def records_path(remote_dir: str | Path, remote: str, shared_run_id: str) -> Path:
    """Return the local file-backed shared append log path."""
    return Path(remote_dir) / remote / "runs" / shared_run_id / "records.jsonl"


def read_batches(remote_dir: str | Path, remote: str, shared_run_id: str) -> list[dict[str, Any]]:
    """Read batch envelopes from a file-backed shared append log."""
    path = records_path(remote_dir, remote, shared_run_id)
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
                    "batch_id": item.get("batch_id") or new_sync_id("batch"),
                    "operation": item.get("record_kind", "record"),
                    "records": [
                        {
                            "record_kind": item["record_kind"],
                            "record_id": record_id_for_body(item["record_kind"], item["body"]),
                            "body": item["body"],
                        }
                    ],
                    "actor": item.get("actor", {}),
                    "origin": item.get("origin", {}),
                    "created_at": item.get("created_at"),
                }
            )
    return batches


def flatten_batches(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return flat record dictionaries from batch envelopes."""
    return [
        {
            "record_kind": record["record_kind"],
            "record_id": record.get("record_id")
            or record_id_for_body(record["record_kind"], record["body"]),
            "body": record["body"],
        }
        for batch in batches
        for record in batch["records"]
    ]


def body_key(kind: str, body: dict[str, Any]) -> tuple[str, str]:
    """Return a stable local identity key for a graph record body."""
    if kind == "node":
        return kind, str(body["node_id"])
    if kind == "transition":
        return kind, str(body["transition_id"])
    if kind == "edge":
        return kind, str(body["edge_id"])
    if kind == "payload":
        return kind, str(body["payload_id"])
    if kind == "view":
        return kind, str(body["view_id"])
    raise ValueError(f"unknown sync record kind: {kind!r}")


def record_id_for_body(kind: str, body: dict[str, Any]) -> str:
    """Return the record id encoded in a graph record body."""
    return body_key(kind, body)[1]


def new_sync_id(kind: str) -> str:
    """Return a collision-resistant sync-layer id."""
    return f"{kind}_{uuid.uuid4().hex}"
