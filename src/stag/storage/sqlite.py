"""SQLite run-directory storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from stag.core import _json as _fast_json
from stag.core.graph_view import GraphView
from stag.core.run import RunHandle
from stag.core.run_graph import RunGraph
from stag.core.schema.graph import Node, Transition
from stag.core.schema.payloads import payload_from_dict
from stag.core.schema.requirements import Requirement
from stag.core.schema.work import WorkEvent, work_event_from_dict, work_session_from_dict
from stag.storage._cache import load_cache, save_cache


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
        # Alpha: drop and recreate on schema mismatch rather than migrate.
        con = sqlite3.connect(db_path)
        try:
            _setup_db(con)
            con.execute("DELETE FROM run_meta")
            con.execute(
                "INSERT INTO run_meta(key, data_json) VALUES (?, ?)",
                ("graph", _dumps({"metadata": dict(run.run_graph.metadata)})),
            )
            _replace_records(con, "nodes", "node_id", run.run_graph.nodes.values())
            _replace_records(
                con, "transitions", "transition_id", run.run_graph.transitions.values()
            )
            _replace_records(con, "payloads", "payload_id", run.run_graph.payloads.values())
            _replace_records(con, "views", "view_id", run.run_graph.views.values())
            _replace_records(
                con, "work_sessions", "work_session_id", run.run_graph.work_sessions.values()
            )
            _replace_work_events(con, run.run_graph.work_events)
            con.commit()
        finally:
            con.close()

        save_cache(run_path, self._row_counts(run_path), run.run_graph)
        return run_path

    def load_run(self, run_id: str) -> RunHandle:
        run_path = self.run_path(run_id)
        manifest = _read_json(run_path / "run.json")
        row_counts = self._row_counts(run_path)
        cached_graph = load_cache(run_path, row_counts)
        requirement = _requirement_from_dict(manifest["requirement"])
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
        if not graph.views:
            root_node_id = str(graph.metadata.get("root_node_id") or "n_0000")
            graph.views["main"] = GraphView("view_main", "main", root_node_id)
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
            return (0, 0, 0, 0, 0, 0)
        con = sqlite3.connect(db_path)
        try:
            _setup_db(con)
            return tuple(
                int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "nodes",
                    "transitions",
                    "payloads",
                    "views",
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
        CREATE TABLE IF NOT EXISTS views (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            view_id TEXT UNIQUE NOT NULL,
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
    for data in _rows(con, "views"):
        view = GraphView(
            str(data["view_id"]),
            str(data["name"]),
            str(data["root_node_id"]),
            dict(data.get("metadata") or {}),
        )
        graph.views[view.name] = view
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


def _replace_records(con: sqlite3.Connection, table: str, id_col: str, records) -> None:
    con.execute(f"DELETE FROM {table}")
    for record in records:
        record_id = getattr(record, id_col)
        con.execute(
            f"INSERT INTO {table}({id_col}, data_json) VALUES (?, ?)",
            (record_id, _dumps(record.to_dict())),
        )


def _replace_work_events(con: sqlite3.Connection, events: list[WorkEvent]) -> None:
    con.execute("DELETE FROM work_events")
    for event in events:
        con.execute(
            "INSERT INTO work_events(event_id, data_json) VALUES (?, ?)",
            (event.event_id, _dumps(event.to_dict())),
        )


def _dumps(data: dict[str, Any]) -> str:
    return _fast_json.dumps(data)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _requirement_from_dict(data: dict[str, Any]) -> Requirement:
    return Requirement(
        requirement_id=str(data["requirement_id"]),
        target_type=str(data["target_type"]),
        target_id=str(data["target_id"]),
        constraints=dict(data.get("constraints") or {}),
        metadata=dict(data.get("metadata") or {}),
    )
