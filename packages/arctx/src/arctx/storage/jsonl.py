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
from arctx.core.lanes import apply_lane_status_events
from arctx.storage._cache import fingerprint as _fingerprint, load_cache, save_cache


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
                if data["run_id"] != entry.name:
                    continue
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
        """On-disk row counts, used to ask whether an in-memory graph is complete.

        This is deliberately not the cache key — see `_cache.fingerprint`. Row
        counts answer "did a concurrent writer add rows while I held this
        graph?", which counting does answer; they cannot answer "is this the
        same content?", which is what a cache needs.
        """
        counts = []
        for name in ("nodes", "steps", "payloads", "lanes", "work_events"):
            path = run_path / f"{name}.jsonl"
            if not path.exists():
                counts.append(0)
            else:
                with path.open("r", encoding="utf-8") as fh:
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
            # the next load rebuild it.
            mem_counts = (
                len(run.run_graph.nodes),
                len(run.run_graph.steps),
                len(run.run_graph.payloads),
                len(run.run_graph.lanes),
                len(run.run_graph.work_events),
            )
            if mem_counts == self._row_counts(run_path):
                save_cache(run_path, _fingerprint(run_path), run.run_graph)

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
        _ensure_manifest_run_id(run_path, manifest, run_id)
        requirement = requirement_from_dict(manifest["requirement"])

        # --- Cache fast path ---
        cache_fingerprint = _fingerprint(run_path)
        cached_graph = load_cache(run_path, cache_fingerprint)
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

        # `.arctx/` is committed and jsonl files use `merge=union`, so a merged
        # working tree can contain duplicated lines in arbitrary order. Loading
        # must therefore be idempotent and order-independent:
        #   * duplicate rows sharing an id are deduped, FIRST occurrence wins
        #     (records are immutable and append-only, so any copy is equivalent;
        #     first-wins simply makes the result independent of line order);
        #   * each collection is loaded in full before the collection that
        #     references it (nodes -> steps -> payloads), so a step may appear
        #     on a line before the node it consumes;
        #   * work events are sorted by (seq, created_at, event_id) rather than
        #     trusting file order;
        #   * graph records are then re-ordered by the work event that created
        #     them (`WorkEvent.created_records`), which is the append-only
        #     ledger of *when* each record came into being. That restores the
        #     recording order the in-memory graph relies on -- notably
        #     cut/uncut supersession ("last marker wins") in core/cuts.py.
        #     Records with no creating event (core-API writes that pass no
        #     user/lane) keep their file order, after the ranked ones.
        event_rows: list[dict[str, Any]] = []
        for epath in [run_path / "lane_events.jsonl", run_path / "work_events.jsonl"]:
            if epath.exists():
                event_rows.extend(self._read_jsonl(epath))
        event_rows = _sort_event_rows(_dedup_rows(event_rows, "event_id"))
        rank = _record_rank(event_rows)

        for row in _ordered_rows(self._read_jsonl(run_path / "nodes.jsonl"), "node_id", rank):
            graph.nodes[row["node_id"]] = Node(
                node_id=row["node_id"],
                metadata=dict(row.get("metadata") or {}),
            )

        for row in _ordered_rows(self._read_jsonl(run_path / "steps.jsonl"), "step_id", rank):
            step = Step(
                step_id=row["step_id"],
                input_node_ids=tuple(row.get("input_node_ids") or []),
                output_node_id=str(row.get("output_node_id") or ""),
                metadata=dict(row.get("metadata") or {}),
            )
            graph.add_step(step)

        for row in _ordered_rows(
            self._read_jsonl(run_path / "payloads.jsonl"), "payload_id", rank
        ):
            payload = payload_from_dict(row)
            graph.payloads[payload.payload_id] = payload
            if payload.target_kind == "node":
                graph.payloads_by_node.setdefault(payload.target_id, []).append(payload.payload_id)
            elif payload.target_kind == "step":
                graph.payloads_by_step.setdefault(payload.target_id, []).append(
                    payload.payload_id
                )

        lane_rows: list[dict[str, Any]] = []
        for lpath in [run_path / "work_sessions.jsonl", run_path / "lanes.jsonl"]:
            if lpath.exists():
                lane_rows.extend(self._read_jsonl(lpath))
        for row in _dedup_rows(lane_rows, "lane_id"):
            session = lane_from_dict(row)
            graph.lanes[session.lane_id] = session

        for row in event_rows:
            graph.work_events.append(work_event_from_dict(row))

        # Fold lane open/close events into status before caching, so both the
        # full-load and cache fast paths report the current lifecycle state.
        apply_lane_status_events(graph)

        save_cache(run_path, cache_fingerprint, graph)

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
        only records whose ID is not present yet are appended. Duplicate rows
        left behind by a git ``merge=union`` are collapsed here, so any write
        also normalises the file. The whole file is written via a temp file +
        fsync + os.replace, so a crash never leaves a torn line. Callers must
        hold the run lock.
        """
        existing = _dedup_rows(JsonlRunStore._read_jsonl(path), id_attr)
        seen = {str(row[id_attr]) for row in existing}
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


def _dedup_rows(rows: list[dict[str, Any]], id_key: str) -> list[dict[str, Any]]:
    """Drop rows repeating an already-seen *id_key*, keeping the first.

    Constraint this relies on: records are immutable once written (append-only,
    opaque ids), so two rows with the same id are byte-identical copies and
    "first wins" is indistinguishable from "last wins". Rows missing *id_key*
    are dropped — they cannot be addressed and are never valid records.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if id_key not in row:
            continue
        rid = str(row[id_key])
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out


def _sort_event_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order work-event rows deterministically, ignoring file order.

    Mirrors ``arctx.core.lanes._event_order``: ``seq`` when present, then the
    creation timestamp, then the opaque event id as a final tiebreak.
    """

    def key(row: dict[str, Any]) -> tuple[int, str, str]:
        seq = row.get("seq")
        return (
            int(seq) if seq is not None else -1,
            str(row.get("created_at") or ""),
            str(row.get("event_id") or ""),
        )

    return sorted(rows, key=key)


def _record_rank(event_rows: list[dict[str, Any]]) -> dict[str, int]:
    """Map record_id -> creation rank, from ordered work-event rows.

    ``WorkEvent.created_records`` is the append-only ledger of which records a
    given event brought into being, so walking the events in their canonical
    order yields a total order over the records they created that does not
    depend on jsonl line order at all.
    """
    rank: dict[str, int] = {}
    for row in event_rows:
        for record_id in row.get("created_records") or ():
            rid = str(record_id)
            if rid not in rank:
                rank[rid] = len(rank)
    return rank


def _ordered_rows(
    rows: list[dict[str, Any]], id_key: str, rank: dict[str, int]
) -> list[dict[str, Any]]:
    """Dedupe *rows* by *id_key* and put them in canonical creation order.

    Ranked records (those a work event claims to have created) follow the event
    order. Unranked records sort ahead of them, keeping their relative file
    order: the only unranked records a CLI-written run has are bootstrap ones
    (the run root node), which do precede every event. A run written purely
    through the core API passes no user/lane, records no events, and therefore
    has an empty *rank* — every row is unranked and file order is preserved.
    """
    deduped = _dedup_rows(rows, id_key)
    return sorted(deduped, key=lambda row: rank.get(str(row[id_key]), -1))


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
    work_event_ids = _ids_from_jsonl(run_path / "work_events.jsonl", "event_id")
    work_event_ids.update(_ids_from_jsonl(run_path / "lane_events.jsonl", "event_id"))
    return {
        "node": _ids_from_jsonl(run_path / "nodes.jsonl", "node_id"),
        "step": _ids_from_jsonl(run_path / "steps.jsonl", "step_id"),
        "payload": _ids_from_jsonl(run_path / "payloads.jsonl", "payload_id"),
        "lanes": _ids_from_jsonl(run_path / "lanes.jsonl", "lane_id"),
        "work_events": work_event_ids,
    }


def _ids_from_jsonl(path: Path, key: str) -> set[str]:
    if not path.exists():
        return set()
    return {
        str(row[key])
        for row in JsonlRunStore._read_jsonl(path)
        if key in row
    }


def _ensure_manifest_run_id(run_path: Path, manifest: dict[str, Any], expected_run_id: str) -> None:
    actual = manifest.get("run_id")
    if actual != expected_run_id:
        raise ValueError(
            f"run manifest mismatch at {run_path}: "
            f"directory is {expected_run_id!r} but run.json has {actual!r}"
        )


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
