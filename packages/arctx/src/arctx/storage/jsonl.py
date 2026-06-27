"""JSONL run-directory storage."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from arctx.core import _json as _fast_json
from arctx.core.append import AppendBatch, AppendResult, GraphRecordEnvelope
from arctx.core.run import RunHandle
from arctx.core.run_graph import RunGraph
from arctx.core.schema.graph import Node, Step
from arctx.core.schema.payloads import payload_from_dict
from arctx.core.schema.requirements import requirement_from_dict
from arctx.core.schema.work import work_event_from_dict, lane_from_dict
from arctx.storage._cache import load_cache, save_cache


class JsonlRunStore:
    """Store a run as a directory of JSON and JSONL files."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def run_path(self, run_id: str) -> Path:
        return self.root / run_id

    def list_runs(self) -> list[dict]:
        if not self.root.exists():
            return []
        runs: list[dict] = []
        for entry in sorted(self.root.iterdir()):
            if not entry.is_dir():
                continue
            run_json = entry / "run.json"
            if not run_json.exists():
                continue
            try:
                data = json.loads(run_json.read_text(encoding="utf-8"))
                runs.append(
                    {
                        "run_id": data["run_id"],
                        "requirement_id": data["requirement"]["requirement_id"],
                        "target_type": data["requirement"]["target_type"],
                        "target_id": data["requirement"]["target_id"],
                    }
                )
            except (KeyError, json.JSONDecodeError):
                continue
        return runs

    def _row_counts(self, run_path: Path) -> tuple[int, ...]:
        """Return current on-disk row counts for the JSONL collections."""
        counts = []
        for name in (
            "nodes",
            "steps",
            "payloads",
            "lanes",
            "work_events",
        ):
            p = run_path / f"{name}.jsonl"
            if not p.exists():
                counts.append(0)
            else:
                with p.open("r", encoding="utf-8") as fh:
                    counts.append(sum(1 for line in fh if line.strip()))
        return tuple(counts)

    def save_run(self, run: RunHandle) -> Path:
        run_path = self.run_path(run.run_id)
        run_path.mkdir(parents=True, exist_ok=True)

        with _run_lock(run_path):
            self._write_json(
                run_path / "run.json",
                {
                    "run_id": run.run_id,
                    "requirement": run.requirement.to_dict(),
                    "counters": dict(run._counters),
                },
            )
            self._write_json(
                run_path / "graph.json",
                {"metadata": dict(run.run_graph.metadata)},
            )
            self._merge_jsonl(
                run_path / "nodes.jsonl", run.run_graph.nodes.values(), "node_id"
            )
            self._merge_jsonl(
                run_path / "steps.jsonl",
                run.run_graph.steps.values(),
                "step_id",
            )
            self._merge_jsonl(
                run_path / "payloads.jsonl",
                run.run_graph.payloads.values(),
                "payload_id",
            )
            self._merge_jsonl(
                run_path / "lanes.jsonl",
                run.run_graph.lanes.values(),
                "lane_id",
            )
            self._merge_jsonl(
                run_path / "work_events.jsonl",
                run.run_graph.work_events,
                "event_id",
            )

            # Only refresh the cache when the in-memory graph matches disk
            # exactly. If a concurrent writer added records, disk is a superset
            # and caching the in-memory graph would under-report; skip and let
            # the row-count mismatch trigger a rebuild on next load.
            mem_counts = (
                len(run.run_graph.nodes),
                len(run.run_graph.steps),
                len(run.run_graph.payloads),
                len(run.run_graph.lanes),
                len(run.run_graph.work_events),
            )
            disk_counts = self._row_counts(run_path)
            if mem_counts == disk_counts:
                save_cache(run_path, disk_counts, run.run_graph)

        return run_path

    def append_batch(self, batch: AppendBatch) -> AppendResult:
        """Atomically append one lane batch to an existing run."""
        run_path = self.run_path(batch.run_id)
        if not (run_path / "run.json").exists():
            raise KeyError(f"unknown run_id: {batch.run_id}")
        run_path.mkdir(parents=True, exist_ok=True)

        with _run_lock(run_path):
            existing = _existing_ids(run_path)
            # Lanes have open membership — no owner lock. A different actor
            # appending to a shared lane is expected, not an error; the lane
            # record is idempotent (added only if its id is new).
            if batch.lane.lane_id not in existing["lanes"]:
                _append_dicts(
                    run_path / "lanes.jsonl",
                    [batch.lane.to_dict()],
                )
                existing["lanes"].add(batch.lane.lane_id)

            appended_records: list[str] = []
            for record in batch.records:
                if record.record_id in existing[record.record_kind]:
                    continue
                _append_dicts(
                    run_path / _record_file(record),
                    [record.record.to_dict()],
                )
                existing[record.record_kind].add(record.record_id)
                appended_records.append(record.record_id)

            next_seq = len(existing["work_events"]) + 1
            event_ids: list[str] = []
            event_seqs: list[int] = []
            event_rows: list[dict[str, Any]] = []
            for event in batch.events:
                if event.event_id in existing["work_events"]:
                    continue
                data = event.to_dict()
                data["seq"] = next_seq
                event_rows.append(data)
                event_ids.append(event.event_id)
                event_seqs.append(next_seq)
                existing["work_events"].add(event.event_id)
                next_seq += 1
            _append_dicts(run_path / "work_events.jsonl", event_rows)

            return AppendResult(
                event_id=event_ids[0] if event_ids else "",
                event_seq=event_seqs[0] if event_seqs else 0,
                record_ids=tuple(appended_records),
                event_ids=tuple(event_ids),
                event_seqs=tuple(event_seqs),
            )

    def load_run(self, run_id: str) -> RunHandle:
        run_path = self.run_path(run_id)
        manifest = self._read_json(run_path / "run.json")
        requirement = requirement_from_dict(manifest["requirement"])

        # --- Cache fast path ---
        row_counts = self._row_counts(run_path)
        cached_graph = load_cache(run_path, row_counts)
        if cached_graph is not None:
            return RunHandle(
                run_id=manifest["run_id"],
                requirement=requirement,
                run_graph=cached_graph,
                _counters={str(k): int(v) for k, v in manifest.get("counters", {}).items()},
            )

        # --- Full load ---
        graph = RunGraph()
        if (run_path / "graph.json").exists():
            gdata = self._read_json(run_path / "graph.json")
            graph.metadata = dict(gdata.get("metadata") or {})

        for row in self._read_jsonl(run_path / "nodes.jsonl"):
            graph.nodes[row["node_id"]] = Node(
                node_id=row["node_id"],
                metadata=dict(row.get("metadata") or {}),
            )

        for row in self._read_jsonl(run_path / "steps.jsonl"):
            step = Step(
                step_id=row["step_id"],
                input_node_ids=tuple(row.get("input_node_ids") or []),
                output_node_id=str(row.get("output_node_id") or ""),
                metadata=dict(row.get("metadata") or {}),
            )
            graph.add_step(step)

        for row in self._read_jsonl(run_path / "payloads.jsonl"):
            payload = payload_from_dict(row)
            graph.payloads[payload.payload_id] = payload
            if payload.target_kind == "node":
                graph.payloads_by_node.setdefault(payload.target_id, []).append(payload.payload_id)
            elif payload.target_kind == "step":
                graph.payloads_by_step.setdefault(payload.target_id, []).append(
                    payload.payload_id
                )

        for lpath in [run_path / "work_sessions.jsonl", run_path / "lanes.jsonl"]:
            if lpath.exists():
                for row in self._read_jsonl(lpath):
                    session = lane_from_dict(row)
                    graph.lanes[session.lane_id] = session

        for epath in [run_path / "lane_events.jsonl", run_path / "work_events.jsonl"]:
            if epath.exists():
                for row in self._read_jsonl(epath):
                    graph.work_events.append(work_event_from_dict(row))

        save_cache(run_path, row_counts, graph)

        return RunHandle(
            run_id=manifest["run_id"],
            requirement=requirement,
            run_graph=graph,
            _counters={str(k): int(v) for k, v in manifest.get("counters", {}).items()},
        )

    @staticmethod
    def _merge_jsonl(path: Path, records, id_attr: str) -> None:
        """Atomically rewrite *path* as the union (by ID) of disk rows and *records*.

        Rows already on disk are kept (including any a concurrent writer added);
        only records whose ID is not present yet are appended. The whole file is
        written via a temp file + fsync + os.replace, so a crash never leaves a
        torn line. Callers must hold the run lock.
        """
        existing = JsonlRunStore._read_jsonl(path)
        seen = {str(row[id_attr]) for row in existing if id_attr in row}
        merged = list(existing)
        for rec in records:
            rid = str(getattr(rec, id_attr))
            if rid in seen:
                continue
            seen.add(rid)
            merged.append(rec.to_dict())
        _atomic_write_text(path, "".join(_fast_json.dumps(row) + "\n" for row in merged))

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        _atomic_write_text(
            path,
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [
            _fast_json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def _atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* atomically and durably (temp + fsync + replace)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextlib.contextmanager
def _run_lock(run_path: Path):
    lock_path = run_path / ".append.lock"
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _existing_ids(run_path: Path) -> dict[str, set[str]]:
    return {
        "node": _ids_from_jsonl(run_path / "nodes.jsonl", "node_id"),
        "step": _ids_from_jsonl(run_path / "steps.jsonl", "step_id"),
        "payload": _ids_from_jsonl(run_path / "payloads.jsonl", "payload_id"),
        "lanes": _ids_from_jsonl(run_path / "lanes.jsonl", "lane_id"),
        "work_events": _ids_from_jsonl(run_path / "lane_events.jsonl", "event_id"),
    }


def _ids_from_jsonl(path: Path, key: str) -> set[str]:
    if not path.exists():
        return set()
    return {
        str(row[key])
        for row in JsonlRunStore._read_jsonl(path)
        if key in row
    }


def _record_file(record: GraphRecordEnvelope) -> str:
    return {
        "node": "nodes.jsonl",
        "step": "steps.jsonl",
        "payload": "payloads.jsonl",
    }[record.record_kind]


def _append_dicts(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    mode = "a" if path.exists() else "w"
    with path.open(mode, encoding="utf-8") as f:
        for row in rows:
            f.write(_fast_json.dumps(row) + "\n")
