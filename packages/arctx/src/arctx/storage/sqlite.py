"""SQLite run-directory storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from arctx.core import _json as _fast_json
from arctx.core.append import AppendBatch, AppendResult
from arctx.core.run import RunHandle
from arctx.core.run_graph import RunGraph
from arctx.core.schema.graph import Node, Transition
from arctx.core.schema.payloads import payload_from_dict
from arctx.core.schema.requirements import requirement_from_dict
from arctx.core.schema.work import WorkEvent, work_event_from_dict, work_session_from_dict
from arctx.storage._cache import load_cache, save_cache


class SqliteRunStore:
    """Store a run as a per-run SQLite database inside a run directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def run_path(self, run_id: str) -> Path:
        return self.root / run_id

    def list_runs(self) -> list[dict]:
        if not self.root.exists():
            return []
        runs: list[dict] = []
        for entry in sorted(self.root.iterdir()):
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

    def save_run(self, run: RunHandle) -> Path:
        run_path = self.run_path(run.run_id)
        run_path.mkdir(parents=True, exist_ok=True)
        _write_json(
            run_path / "run.json",
            {
                "run_id": run.run_id,
                "requirement": run.requirement.to_dict(),
                "counters": dict(run._counters),
            },
        )
        db_path = run_path / "run.db"
        con = sqlite3.connect(db_path, timeout=30)
        try:
            _setup_db(con)
            # Serialize with concurrent writers (append_batch / another
            # save_run) via SQLite's write lock, and merge instead of replacing
            # so a concurrent writer's records are never clobbered.
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM run_meta")
            con.execute(
                "INSERT INTO run_meta(key, data_json) VALUES (?, ?)",
                ("graph", _dumps({"metadata": dict(run.run_graph.metadata)})),
            )
            _merge_records(con, "nodes", "node_id", run.run_graph.nodes.values())
            _merge_records(
                con, "transitions", "transition_id", run.run_graph.transitions.values()
            )
            _merge_records(con, "payloads", "payload_id", run.run_graph.payloads.values())
            _merge_records(
                con, "work_sessions", "work_session_id", run.run_graph.work_sessions.values()
            )
            _merge_work_events(con, run.run_graph.work_events)
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

        # Only refresh the cache when the in-memory graph matches disk exactly;
        # if a concurrent writer added records, disk is a superset, so let the
        # row-count mismatch rebuild the cache on next load.
        mem_counts = (
            len(run.run_graph.nodes),
            len(run.run_graph.transitions),
            len(run.run_graph.payloads),
            len(run.run_graph.work_sessions),
            len(run.run_graph.work_events),
        )
        disk_counts = self._row_counts(run_path)
        if mem_counts == disk_counts:
            save_cache(run_path, disk_counts, run.run_graph)
        return run_path

    def append_batch(self, batch: AppendBatch) -> AppendResult:
        """Atomically append one work-session batch to an existing run."""
        run_path = self.run_path(batch.run_id)
        if not (run_path / "run.json").exists():
            raise KeyError(f"unknown run_id: {batch.run_id}")

        con = sqlite3.connect(run_path / "run.db", timeout=30)
        try:
            _setup_db(con)
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT data_json FROM work_sessions WHERE work_session_id = ?",
                (batch.work_session.work_session_id,),
            ).fetchone()
            if row is not None:
                existing_user = str(json.loads(row[0])["user_id"])
                if existing_user != batch.work_session.user_id:
                    raise ValueError(
                        f"work_session_id {batch.work_session.work_session_id!r} belongs to "
                        f"user {existing_user!r}, not {batch.work_session.user_id!r}"
                    )
            con.execute(
                """
                INSERT OR IGNORE INTO work_sessions(work_session_id, data_json)
                VALUES (?, ?)
                """,
                (
                    batch.work_session.work_session_id,
                    _dumps(batch.work_session.to_dict()),
                ),
            )

            appended_records: list[str] = []
            for record in batch.records:
                table, id_col = _record_table(record.record_kind)
                before = con.total_changes
                con.execute(
                    f"INSERT OR IGNORE INTO {table}({id_col}, data_json) VALUES (?, ?)",
                    (record.record_id, _dumps(record.record.to_dict())),
                )
                if con.total_changes != before:
                    appended_records.append(record.record_id)

            event_ids: list[str] = []
            event_seqs: list[int] = []
            for event in batch.events:
                data = event.to_dict()
                before = con.total_changes
                con.execute(
                    "INSERT OR IGNORE INTO work_events(event_id, data_json) VALUES (?, ?)",
                    (event.event_id, _dumps(data)),
                )
                if con.total_changes != before:
                    seq = int(
                        con.execute(
                            "SELECT seq FROM work_events WHERE event_id = ?",
                            (event.event_id,),
                        ).fetchone()[0]
                    )
                    data["seq"] = seq
                    con.execute(
                        "UPDATE work_events SET data_json = ? WHERE event_id = ?",
                        (_dumps(data), event.event_id),
                    )
                    event_ids.append(event.event_id)
                    event_seqs.append(seq)
            con.commit()
            return AppendResult(
                event_id=event_ids[0] if event_ids else "",
                event_seq=event_seqs[0] if event_seqs else 0,
                record_ids=tuple(appended_records),
                event_ids=tuple(event_ids),
                event_seqs=tuple(event_seqs),
            )
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def load_run(self, run_id: str) -> RunHandle:
        run_path = self.run_path(run_id)
        manifest = _read_json(run_path / "run.json")
        row_counts = self._row_counts(run_path)
        cached_graph = load_cache(run_path, row_counts)
        requirement = requirement_from_dict(manifest["requirement"])
        if cached_graph is not None:
            return RunHandle(
                run_id=manifest["run_id"],
                requirement=requirement,
                run_graph=cached_graph,
                _counters={str(k): int(v) for k, v in manifest.get("counters", {}).items()},
            )

        con = sqlite3.connect(run_path / "run.db")
        try:
            _setup_db(con)
            graph = _load_graph(con)
        finally:
            con.close()
        save_cache(run_path, row_counts, graph)
        return RunHandle(
            run_id=manifest["run_id"],
            requirement=requirement,
            run_graph=graph,
            _counters={str(k): int(v) for k, v in manifest.get("counters", {}).items()},
        )

    def _row_counts(self, run_path: Path) -> tuple[int, ...]:
        db_path = run_path / "run.db"
        if not db_path.exists():
            return (0, 0, 0, 0, 0)
        con = sqlite3.connect(db_path)
        try:
            _setup_db(con)
            return tuple(
                int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "nodes",
                    "transitions",
                    "payloads",
                    "work_sessions",
                    "work_events",
                )
            )
        finally:
            con.close()


def _setup_db(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS run_meta (
            key TEXT PRIMARY KEY,
            data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nodes (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT UNIQUE NOT NULL,
            data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transitions (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            transition_id TEXT UNIQUE NOT NULL,
            data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payloads (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            payload_id TEXT UNIQUE NOT NULL,
            data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS work_sessions (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            work_session_id TEXT UNIQUE NOT NULL,
            data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS work_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            data_json TEXT NOT NULL
        );
        """)


def _load_graph(con: sqlite3.Connection) -> RunGraph:
    graph = RunGraph()
    row = con.execute("SELECT data_json FROM run_meta WHERE key='graph'").fetchone()
    if row:
        graph.metadata = dict(json.loads(row[0]).get("metadata") or {})
    for data in _rows(con, "nodes"):
        graph.nodes[data["node_id"]] = Node(data["node_id"], dict(data.get("metadata") or {}))
    for data in _rows(con, "transitions"):
        graph.add_transition(
            Transition(
                transition_id=data["transition_id"],
                input_node_ids=tuple(data.get("input_node_ids") or []),
                output_node_id=str(data.get("output_node_id") or ""),
                metadata=dict(data.get("metadata") or {}),
            )
        )
    for data in _rows(con, "payloads"):
        payload = payload_from_dict(data)
        graph.payloads[payload.payload_id] = payload
        if payload.target_kind == "node":
            graph.payloads_by_node.setdefault(payload.target_id, []).append(payload.payload_id)
        elif payload.target_kind == "transition":
            graph.payloads_by_transition.setdefault(payload.target_id, []).append(payload.payload_id)
    for data in _rows(con, "work_sessions"):
        session = work_session_from_dict(data)
        graph.work_sessions[session.work_session_id] = session
    for data in _rows(con, "work_events"):
        graph.work_events.append(work_event_from_dict(data))
    return graph


def _rows(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [
        json.loads(row[0]) for row in con.execute(f"SELECT data_json FROM {table} ORDER BY seq ASC")
    ]


def _merge_records(con: sqlite3.Connection, table: str, id_col: str, records) -> None:
    """Insert records by ID, preserving any already present (idempotent merge)."""
    for record in records:
        record_id = getattr(record, id_col)
        con.execute(
            f"INSERT OR IGNORE INTO {table}({id_col}, data_json) VALUES (?, ?)",
            (record_id, _dumps(record.to_dict())),
        )


def _merge_work_events(con: sqlite3.Connection, events: list[WorkEvent]) -> None:
    """Insert work events by ID, preserving any already present."""
    for event in events:
        con.execute(
            "INSERT OR IGNORE INTO work_events(event_id, data_json) VALUES (?, ?)",
            (event.event_id, _dumps(event.to_dict())),
        )


def _dumps(data: dict[str, Any]) -> str:
    return _fast_json.dumps(data)


def _record_table(kind: str) -> tuple[str, str]:
    return {
        "node": ("nodes", "node_id"),
        "transition": ("transitions", "transition_id"),
        "payload": ("payloads", "payload_id"),
    }[kind]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
