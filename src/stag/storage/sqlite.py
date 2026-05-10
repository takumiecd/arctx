"""SQLite run-directory storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from stag.core.graph_view import GraphView
from stag.core.run import RunHandle
from stag.core.run_graph import RunGraph
from stag.core.schema.graph import InputTransition, Node, OutputTransition
from stag.core.schema.payloads import payload_from_dict
from stag.core.schema.requirements import Requirement


class SqliteRunStore:
    """Store a run as a per-run SQLite database inside a directory tree.

    Layout (mirrors JsonlRunStore)::

        <root>/
          <run_id>/
            run.json   – manifest identical to JsonlRunStore (shared by list_runs)
            run.db     – SQLite database with all graph records

    ``run.json`` is kept intentionally identical to the JSONL implementation so
    that ``list_runs()`` can scan a mixed root directory containing both
    JsonlRunStore and SqliteRunStore runs without special-casing.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ------------------------------------------------------------------
    # Protocol: run_path
    # ------------------------------------------------------------------

    def run_path(self, run_id: str) -> Path:
        return self.root / run_id

    # ------------------------------------------------------------------
    # Protocol: list_runs
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Protocol: save_run
    # ------------------------------------------------------------------

    def save_run(self, run: RunHandle) -> Path:
        run_path = self.run_path(run.run_id)
        run_path.mkdir(parents=True, exist_ok=True)

        # Write manifest (same content/format as JsonlRunStore)
        _write_json(
            run_path / "run.json",
            {
                "run_id": run.run_id,
                "requirement": run.requirement.to_dict(),
                "counters": dict(run._counters),
            },
        )

        db_path = run_path / "run.db"
        con = sqlite3.connect(str(db_path))
        try:
            _setup_db(con)

            # run_meta: counters + graph metadata (INSERT OR REPLACE)
            con.execute(
                "INSERT OR REPLACE INTO run_meta(key, value) VALUES (?, ?)",
                (
                    "requirement_json",
                    json.dumps(run.requirement.to_dict(), ensure_ascii=False, sort_keys=True),
                ),
            )
            con.execute(
                "INSERT OR REPLACE INTO run_meta(key, value) VALUES (?, ?)",
                (
                    "counters_json",
                    json.dumps(dict(run._counters), ensure_ascii=False, sort_keys=True),
                ),
            )
            con.execute(
                "INSERT OR REPLACE INTO run_meta(key, value) VALUES (?, ?)",
                (
                    "graph_metadata_json",
                    json.dumps(dict(run.run_graph.metadata), ensure_ascii=False, sort_keys=True),
                ),
            )

            # Delta-insert each collection
            _delta_insert(
                con,
                table="nodes",
                id_col="node_id",
                records=list(run.run_graph.nodes.values()),
                to_dict=lambda n: n.to_dict(),
            )
            _delta_insert(
                con,
                table="input_transitions",
                id_col="input_transition_id",
                records=list(run.run_graph.input_transitions.values()),
                to_dict=lambda it: it.to_dict(),
            )
            _delta_insert(
                con,
                table="output_transitions",
                id_col="output_transition_id",
                records=list(run.run_graph.output_transitions.values()),
                to_dict=lambda ot: ot.to_dict(),
            )
            _delta_insert(
                con,
                table="payloads",
                id_col="payload_id",
                records=list(run.run_graph.payloads.values()),
                to_dict=lambda p: p.to_dict(),
            )
            _delta_insert(
                con,
                table="views",
                id_col="view_id",
                records=list(run.run_graph.views.values()),
                to_dict=lambda v: v.to_dict(),
                extra_cols={"name": lambda v: v.name},
            )

            con.commit()
        finally:
            con.close()

        return run_path

    # ------------------------------------------------------------------
    # Protocol: load_run
    # ------------------------------------------------------------------

    def load_run(self, run_id: str) -> RunHandle:
        run_path = self.run_path(run_id)
        manifest = _read_json(run_path / "run.json")
        requirement = _requirement_from_dict(manifest["requirement"])

        db_path = run_path / "run.db"
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        try:
            graph = RunGraph()

            # Restore graph metadata from run_meta
            meta_row = con.execute(
                "SELECT value FROM run_meta WHERE key = 'graph_metadata_json'"
            ).fetchone()
            if meta_row:
                graph.metadata = dict(json.loads(meta_row["value"]))

            # Nodes (seq ASC preserves insertion order)
            for row in con.execute("SELECT data_json FROM nodes ORDER BY seq ASC"):
                d = json.loads(row["data_json"])
                graph.nodes[d["node_id"]] = Node(
                    node_id=d["node_id"],
                    metadata=dict(d.get("metadata") or {}),
                )

            # InputTransitions
            for row in con.execute(
                "SELECT data_json FROM input_transitions ORDER BY seq ASC"
            ):
                d = json.loads(row["data_json"])
                it = InputTransition(
                    input_transition_id=d["input_transition_id"],
                    input_node_ids=tuple(d.get("input_node_ids") or []),
                    metadata=dict(d.get("metadata") or {}),
                )
                graph.input_transitions[it.input_transition_id] = it
                for nid in it.input_node_ids:
                    graph.input_transitions_from_node.setdefault(nid, []).append(
                        it.input_transition_id
                    )

            # OutputTransitions
            for row in con.execute(
                "SELECT data_json FROM output_transitions ORDER BY seq ASC"
            ):
                d = json.loads(row["data_json"])
                ot = OutputTransition(
                    output_transition_id=d["output_transition_id"],
                    input_transition_id=d["input_transition_id"],
                    to_node_id=d["to_node_id"],
                    metadata=dict(d.get("metadata") or {}),
                )
                graph.output_transitions[ot.output_transition_id] = ot
                graph.output_transitions_from_it.setdefault(
                    ot.input_transition_id, []
                ).append(ot.output_transition_id)
                graph.output_transitions_to_node.setdefault(ot.to_node_id, []).append(
                    ot.output_transition_id
                )

            # Payloads
            for row in con.execute("SELECT data_json FROM payloads ORDER BY seq ASC"):
                d = json.loads(row["data_json"])
                payload = payload_from_dict(d)
                graph.payloads[payload.payload_id] = payload
                if payload.target_kind == "node":
                    graph.payloads_by_node.setdefault(payload.target_id, []).append(
                        payload.payload_id
                    )
                elif payload.target_kind == "input_transition":
                    graph.payloads_by_input_transition.setdefault(
                        payload.target_id, []
                    ).append(payload.payload_id)
                elif payload.target_kind == "output_transition":
                    graph.payloads_by_output_transition.setdefault(
                        payload.target_id, []
                    ).append(payload.payload_id)

            # Views
            for row in con.execute("SELECT data_json FROM views ORDER BY seq ASC"):
                d = json.loads(row["data_json"])
                v = GraphView(
                    view_id=str(d["view_id"]),
                    name=str(d["name"]),
                    root_node_id=str(d["root_node_id"]),
                    metadata=dict(d.get("metadata") or {}),
                )
                graph.views[v.name] = v

            if not graph.views:
                graph.views["main"] = GraphView(
                    view_id="view_main",
                    name="main",
                    root_node_id="n_0000",
                )

        finally:
            con.close()

        return RunHandle(
            run_id=manifest["run_id"],
            requirement=requirement,
            run_graph=graph,
            _counters={str(k): int(v) for k, v in manifest.get("counters", {}).items()},
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _setup_db(con: sqlite3.Connection) -> None:
    """Create tables and enable WAL mode."""
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS run_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            seq       INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id   TEXT UNIQUE,
            data_json TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS input_transitions (
            seq                  INTEGER PRIMARY KEY AUTOINCREMENT,
            input_transition_id  TEXT UNIQUE,
            data_json            TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS output_transitions (
            seq                   INTEGER PRIMARY KEY AUTOINCREMENT,
            output_transition_id  TEXT UNIQUE,
            data_json             TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS payloads (
            seq        INTEGER PRIMARY KEY AUTOINCREMENT,
            payload_id TEXT UNIQUE,
            data_json  TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS views (
            seq       INTEGER PRIMARY KEY AUTOINCREMENT,
            view_id   TEXT UNIQUE,
            name      TEXT UNIQUE,
            data_json TEXT
        )
        """
    )


def _delta_insert(
    con: sqlite3.Connection,
    *,
    table: str,
    id_col: str,
    records: list,
    to_dict,
    extra_cols: dict[str, Any] | None = None,
) -> None:
    """Insert only records that are new since the last save.

    Compares COUNT(*) on disk vs len(records) in memory:
    - disk == mem  → skip
    - disk <  mem  → INSERT the tail (records[disk_count:])
    - disk >  mem  → RuntimeError (external modification / corruption)
    """
    (disk_count,) = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # type: ignore[misc]
    mem_count = len(records)

    if disk_count > mem_count:
        raise RuntimeError(
            f"{table}: disk has {disk_count} rows but memory has {mem_count} records. "
            "The run database may be corrupt or was modified externally."
        )

    new_records = records[disk_count:]
    if not new_records:
        return

    if extra_cols:
        col_names = ", ".join([id_col, "data_json"] + list(extra_cols.keys()))
        placeholders = ", ".join(["?"] * (2 + len(extra_cols)))
        sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
        for rec in new_records:
            data = to_dict(rec)
            extra_vals = [fn(rec) for fn in extra_cols.values()]
            con.execute(
                sql,
                [data[id_col], json.dumps(data, ensure_ascii=False, sort_keys=True)]
                + extra_vals,
            )
    else:
        sql = f"INSERT INTO {table} ({id_col}, data_json) VALUES (?, ?)"
        for rec in new_records:
            data = to_dict(rec)
            con.execute(
                sql,
                (
                    data[id_col],
                    json.dumps(data, ensure_ascii=False, sort_keys=True),
                ),
            )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _requirement_from_dict(data: dict[str, Any]) -> Requirement:
    return Requirement(
        requirement_id=data["requirement_id"],
        target_type=data["target_type"],
        target_id=data["target_id"],
        objective=dict(data.get("objective") or {}),
        constraints=dict(data.get("constraints") or {}),
        metadata=dict(data.get("metadata") or {}),
    )
