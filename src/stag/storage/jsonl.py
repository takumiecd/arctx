"""JSONL run-directory storage."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

from stag.core import _json as _fast_json
from stag.core.graph_view import GraphView
from stag.core.run import RunHandle
from stag.core.run_graph import RunGraph
from stag.core.schema.graph import Node, Transition
from stag.core.schema.payloads import payload_from_dict
from stag.core.schema.requirements import Requirement
from stag.core.schema.work import work_event_from_dict, work_session_from_dict
from stag.storage._cache import load_cache, save_cache


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
            "transitions",
            "payloads",
            "views",
            "work_sessions",
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
        self._append_jsonl(
            run_path / "nodes.jsonl",
            list(run.run_graph.nodes.values()),
            lambda node: node.to_dict(),
        )
        self._append_jsonl(
            run_path / "transitions.jsonl",
            list(run.run_graph.transitions.values()),
            lambda transition: transition.to_dict(),
        )
        self._append_jsonl(
            run_path / "payloads.jsonl",
            list(run.run_graph.payloads.values()),
            lambda payload: payload.to_dict(),
        )
        self._append_jsonl(
            run_path / "views.jsonl",
            list(run.run_graph.views.values()),
            lambda v: v.to_dict(),
        )
        self._append_jsonl(
            run_path / "work_sessions.jsonl",
            list(run.run_graph.work_sessions.values()),
            lambda s: s.to_dict(),
        )
        self._append_jsonl(
            run_path / "work_events.jsonl",
            list(run.run_graph.work_events),
            lambda e: e.to_dict(),
        )

        row_counts = (
            len(run.run_graph.nodes),
            len(run.run_graph.transitions),
            len(run.run_graph.payloads),
            len(run.run_graph.views),
            len(run.run_graph.work_sessions),
            len(run.run_graph.work_events),
        )
        save_cache(run_path, row_counts, run.run_graph)

        return run_path

    def load_run(self, run_id: str) -> RunHandle:
        run_path = self.run_path(run_id)
        manifest = self._read_json(run_path / "run.json")
        requirement = _requirement_from_dict(manifest["requirement"])

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

        for row in self._read_jsonl(run_path / "transitions.jsonl"):
            transition = Transition(
                transition_id=row["transition_id"],
                input_node_ids=tuple(row.get("input_node_ids") or []),
                output_node_id=str(row.get("output_node_id") or ""),
                metadata=dict(row.get("metadata") or {}),
            )
            graph.add_transition(transition)

        for row in self._read_jsonl(run_path / "payloads.jsonl"):
            payload = payload_from_dict(row)
            graph.payloads[payload.payload_id] = payload
            if payload.target_kind == "node":
                graph.payloads_by_node.setdefault(payload.target_id, []).append(payload.payload_id)
            elif payload.target_kind == "transition":
                graph.payloads_by_transition.setdefault(payload.target_id, []).append(
                    payload.payload_id
                )

        for row in self._read_jsonl(run_path / "views.jsonl"):
            v = GraphView(
                view_id=str(row["view_id"]),
                name=str(row["name"]),
                root_node_id=str(row["root_node_id"]),
                metadata=dict(row.get("metadata") or {}),
            )
            graph.views[v.name] = v

        for row in self._read_jsonl(run_path / "work_sessions.jsonl"):
            session = work_session_from_dict(row)
            graph.work_sessions[session.work_session_id] = session

        for row in self._read_jsonl(run_path / "work_events.jsonl"):
            graph.work_events.append(work_event_from_dict(row))

        if not graph.views:
            root_node_id = str(graph.metadata.get("root_node_id") or "n_0000")
            graph.views["main"] = GraphView(
                view_id="view_main",
                name="main",
                root_node_id=root_node_id,
            )

        save_cache(run_path, row_counts, graph)

        return RunHandle(
            run_id=manifest["run_id"],
            requirement=requirement,
            run_graph=graph,
            _counters={str(k): int(v) for k, v in manifest.get("counters", {}).items()},
        )

    @staticmethod
    def _append_jsonl(path: Path, records: list, to_dict) -> None:
        """Append only new records to a JSONL file."""
        disk_count = 0
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                disk_count = sum(1 for line in f if line.strip())

        mem_count = len(records)
        if disk_count > mem_count:
            raise RuntimeError(
                f"{path.name}: disk has {disk_count} lines but memory has {mem_count} records. "
                "The run directory may be corrupt or was modified externally."
            )

        new_records = list(itertools.islice(records, disk_count, None))
        if not new_records:
            return

        mode = "a" if disk_count > 0 else "w"
        with path.open(mode, encoding="utf-8") as f:
            for rec in new_records:
                f.write(_fast_json.dumps(to_dict(rec)) + "\n")

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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


def _requirement_from_dict(data: dict[str, Any]) -> Requirement:
    return Requirement(
        requirement_id=data["requirement_id"],
        target_type=data["target_type"],
        target_id=data["target_id"],
        objective=dict(data.get("objective") or {}),
        constraints=dict(data.get("constraints") or {}),
        metadata=dict(data.get("metadata") or {}),
    )
