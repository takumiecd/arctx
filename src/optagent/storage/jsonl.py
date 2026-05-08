"""JSONL run-directory storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from optagent.core.graph_view import GraphView
from optagent.core.run import RunHandle
from optagent.core.run.handle import init as _init_handle
from optagent.core.run_graph import RunGraph
from optagent.core.schema.graph import InputTransition, Node, OutputTransition
from optagent.core.schema.payloads import payload_from_dict
from optagent.core.schema.requirements import Requirement


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
        self._write_jsonl(
            run_path / "nodes.jsonl",
            (node.to_dict() for node in run.run_graph.nodes.values()),
        )
        self._write_jsonl(
            run_path / "input_transitions.jsonl",
            (it.to_dict() for it in run.run_graph.input_transitions.values()),
        )
        self._write_jsonl(
            run_path / "output_transitions.jsonl",
            (ot.to_dict() for ot in run.run_graph.output_transitions.values()),
        )
        self._write_jsonl(
            run_path / "payloads.jsonl",
            (payload.to_dict() for payload in run.run_graph.payloads.values()),
        )
        self._write_jsonl(
            run_path / "views.jsonl",
            (v.to_dict() for v in run.views.values()),
        )
        return run_path

    def load_run(self, run_id: str) -> RunHandle:
        run_path = self.run_path(run_id)
        manifest = self._read_json(run_path / "run.json")
        requirement = _requirement_from_dict(manifest["requirement"])

        graph = RunGraph()
        if (run_path / "graph.json").exists():
            gdata = self._read_json(run_path / "graph.json")
            graph.metadata = dict(gdata.get("metadata") or {})

        for row in self._read_jsonl(run_path / "nodes.jsonl"):
            graph.nodes[row["node_id"]] = Node(
                node_id=row["node_id"],
                metadata=dict(row.get("metadata") or {}),
            )

        for row in self._read_jsonl(run_path / "input_transitions.jsonl"):
            it = InputTransition(
                input_transition_id=row["input_transition_id"],
                input_node_ids=tuple(row.get("input_node_ids") or []),
                metadata=dict(row.get("metadata") or {}),
            )
            graph.input_transitions[it.input_transition_id] = it
            for nid in it.input_node_ids:
                graph.input_transitions_from_node.setdefault(nid, []).append(
                    it.input_transition_id
                )

        for row in self._read_jsonl(run_path / "output_transitions.jsonl"):
            ot = OutputTransition(
                output_transition_id=row["output_transition_id"],
                input_transition_id=row["input_transition_id"],
                to_node_id=row["to_node_id"],
                metadata=dict(row.get("metadata") or {}),
            )
            graph.output_transitions[ot.output_transition_id] = ot
            graph.output_transitions_from_it.setdefault(ot.input_transition_id, []).append(
                ot.output_transition_id
            )
            graph.output_transitions_to_node.setdefault(ot.to_node_id, []).append(
                ot.output_transition_id
            )

        for row in self._read_jsonl(run_path / "payloads.jsonl"):
            payload = payload_from_dict(row)
            graph.payloads[payload.payload_id] = payload
            if payload.target_kind == "node":
                graph.payloads_by_node.setdefault(payload.target_id, []).append(
                    payload.payload_id
                )
            elif payload.target_kind == "input_transition":
                graph.payloads_by_input_transition.setdefault(payload.target_id, []).append(
                    payload.payload_id
                )
            elif payload.target_kind == "output_transition":
                graph.payloads_by_output_transition.setdefault(payload.target_id, []).append(
                    payload.payload_id
                )

        views: dict[str, GraphView] = {}
        for row in self._read_jsonl(run_path / "views.jsonl"):
            v = GraphView(
                view_id=str(row["view_id"]),
                name=str(row["name"]),
                root_node_ids=tuple(row.get("root_node_ids") or []),
                node_ids=set(row.get("node_ids") or []),
                input_transition_ids=set(row.get("input_transition_ids") or []),
                output_transition_ids=set(row.get("output_transition_ids") or []),
                payload_ids=set(row.get("payload_ids") or []),
                metadata=dict(row.get("metadata") or {}),
            )
            views[v.name] = v

        if not views:
            from optagent.core.graph_view import GraphView as GV
            main = GV(
                view_id="view_main",
                name="main",
                root_node_ids=("n_0000",),
                node_ids={"n_0000"},
            )
            views["main"] = main

        return RunHandle(
            run_id=manifest["run_id"],
            requirement=requirement,
            run_graph=graph,
            views=views,
            _counters={str(k): int(v) for k, v in manifest.get("counters", {}).items()},
        )

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_jsonl(path: Path, rows) -> None:
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [
            json.loads(line)
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
