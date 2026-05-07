"""JSONL run-directory storage."""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any

from optagent.core.schema.derived import DerivedRecord
from optagent.core.schema.plans import ExecutionPlan, PredictionPlan
from optagent.core.schema.requirements import Requirement
from optagent.core.schema.results import ActionResult
from optagent.core.run import RunHandle
from optagent.core.schema.state import (
    ArtifactRef,
    Budget,
    FindingRef,
    PredictionRef,
    StateNode,
    StateSnapshot,
)
from optagent.core.dag import PredictionDAG, TraceDAG
from optagent.core.schema.transitions import (
    ObservedTransition,
    PredictedTransition,
    PredictionMatch,
    TraceCut,
)


class JsonlRunStore:
    """Store a run as a directory of JSON and JSONL files."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def run_path(self, run_id: str) -> Path:
        return self.root / run_id

    def list_runs(self) -> list[dict]:
        """Return a list of run summaries from the store root.

        Each summary contains run_id and requirement fields. Invalid run
        directories are skipped.
        """
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
        """Write the whole run snapshot to a run directory."""

        run_path = self.run_path(run.run_id)
        run_path.mkdir(parents=True, exist_ok=True)

        self._write_json(
            run_path / "run.json",
            {
                "run_id": run.run_id,
                "requirement": run.requirement.to_dict(),
                "counters": dict(run._counters),
                "trace_dag": {
                    "dag_id": run.trace_dag.dag_id,
                },
                "prediction_dag": {
                    "dag_id": run.prediction_dag.dag_id,
                    "anchor_observed_state_id": run.prediction_dag.anchor_observed_state_id,
                    "root_predicted_state_id": run.prediction_dag.root_predicted_state_id,
                    "stale": run.prediction_dag.stale,
                },
            },
        )
        self._write_jsonl(run_path / "states.jsonl", self._state_rows(run))
        self._write_jsonl(
            run_path / "execution_plans.jsonl",
            (plan.to_dict() for plan in run.trace_dag.execution_plans.values()),
        )
        self._write_jsonl(
            run_path / "prediction_plans.jsonl",
            (plan.to_dict() for plan in run.prediction_dag.plans.values()),
        )
        self._write_jsonl(
            run_path / "predicted_transitions.jsonl",
            (transition.to_dict() for transition in run.prediction_dag.transitions.values()),
        )
        self._write_jsonl(
            run_path / "observed_transitions.jsonl",
            (transition.to_dict() for transition in run.trace_dag.transitions.values()),
        )
        self._write_jsonl(run_path / "derived_records.jsonl", self._derived_rows(run))
        self._write_jsonl(
            run_path / "trace_cuts.jsonl",
            (run.trace_dag.cuts[cid].to_dict() for cid in run.trace_dag.cut_order),
        )
        return run_path

    def load_run(self, run_id: str) -> RunHandle:
        """Load a run snapshot from a run directory."""

        run_path = self.run_path(run_id)
        manifest = self._read_json(run_path / "run.json")
        requirement = _requirement_from_dict(manifest["requirement"])

        trace_dag = TraceDAG(dag_id=manifest["trace_dag"]["dag_id"])
        prediction_dag = PredictionDAG(
            dag_id=manifest["prediction_dag"]["dag_id"],
            anchor_observed_state_id=manifest["prediction_dag"]["anchor_observed_state_id"],
            root_predicted_state_id=manifest["prediction_dag"]["root_predicted_state_id"],
            stale=bool(manifest["prediction_dag"].get("stale", False)),
        )

        for row in self._read_jsonl(run_path / "states.jsonl"):
            node = _state_node_from_dict(row["record"])
            if row["dag"] == "trace":
                trace_dag.add_node(node, depth=int(row["depth"]))
            elif row["dag"] == "prediction":
                prediction_dag.add_node(node, depth=int(row["depth"]))
            else:
                raise ValueError(f"unknown state dag: {row['dag']}")

        for row in self._read_jsonl(run_path / "execution_plans.jsonl"):
            plan = _execution_plan_from_dict(row)
            trace_dag.add_execution_plan(plan)

        for row in self._read_jsonl(run_path / "prediction_plans.jsonl"):
            prediction_dag.add_plan(_prediction_plan_from_dict(row))

        for row in self._read_jsonl(run_path / "predicted_transitions.jsonl"):
            prediction_dag.add_transition(_predicted_transition_from_dict(row))

        for row in self._read_jsonl(run_path / "observed_transitions.jsonl"):
            trace_dag.append_transition(_observed_transition_from_dict(row))

        for row in self._read_jsonl(run_path / "trace_cuts.jsonl"):
            trace_dag.add_cut(_trace_cut_from_dict(row))

        return RunHandle(
            run_id=manifest["run_id"],
            requirement=requirement,
            trace_dag=trace_dag,
            prediction_dag=prediction_dag,
            _counters={str(k): int(v) for k, v in manifest.get("counters", {}).items()},
        )

    def _state_rows(self, run: RunHandle):
        for state_id, node in run.trace_dag.nodes.items():
            yield {
                "dag": "trace",
                "state_id": state_id,
                "depth": run.trace_dag.node_depths[state_id],
                "record": node.to_dict(),
            }
        for state_id, node in run.prediction_dag.nodes.items():
            yield {
                "dag": "prediction",
                "state_id": state_id,
                "depth": run.prediction_dag.node_depths[state_id],
                "record": node.to_dict(),
            }

    def _derived_rows(self, run: RunHandle):
        seen: set[str] = set()
        for transition in run.trace_dag.transitions.values():
            for record in transition.derived_records:
                if record.derived_id not in seen:
                    seen.add(record.derived_id)
                    yield record.to_dict()

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
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _pick_fields(cls, data: dict[str, Any]) -> dict[str, Any]:
    names = {field.name for field in fields(cls)}
    return {name: data[name] for name in names if name in data}


def _tuple(value: Any) -> tuple:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _requirement_from_dict(data: dict[str, Any]) -> Requirement:
    return Requirement(**_pick_fields(Requirement, data))


def _artifact_ref_from_dict(data: dict[str, Any]) -> ArtifactRef:
    return ArtifactRef(**_pick_fields(ArtifactRef, data))


def _finding_ref_from_dict(data: dict[str, Any]) -> FindingRef:
    return FindingRef(**_pick_fields(FindingRef, data))


def _prediction_ref_from_dict(data: dict[str, Any]) -> PredictionRef:
    return PredictionRef(**_pick_fields(PredictionRef, data))


def _budget_from_dict(data: dict[str, Any] | None) -> Budget | None:
    if data is None:
        return None
    return Budget(**_pick_fields(Budget, data))


def _snapshot_from_dict(data: dict[str, Any]) -> StateSnapshot:
    return StateSnapshot(
        requirement=_requirement_from_dict(data["requirement"]),
        artifacts=tuple(_artifact_ref_from_dict(item) for item in data.get("artifacts", ())),
        knowledge=tuple(_finding_ref_from_dict(item) for item in data.get("knowledge", ())),
        open_questions=_tuple(data.get("open_questions")),
        active_branches=_tuple(data.get("active_branches")),
        predictions=tuple(_prediction_ref_from_dict(item) for item in data.get("predictions", ())),
        budget=_budget_from_dict(data.get("budget")),
        metadata=dict(data.get("metadata", {})),
    )


def _state_node_from_dict(data: dict[str, Any]) -> StateNode:
    return StateNode(
        state_id=data["state_id"],
        state_kind=data["state_kind"],
        snapshot=_snapshot_from_dict(data["snapshot"]),
        snapshot_hash=data.get("snapshot_hash"),
        anchor_observed_state_id=data.get("anchor_observed_state_id"),
        assumptions=_tuple(data.get("assumptions")),
        confidence=data.get("confidence"),
        status=data.get("status", "active"),
        metadata=dict(data.get("metadata", {})),
    )


def _execution_plan_from_dict(data: dict[str, Any]) -> ExecutionPlan:
    return ExecutionPlan(
        **{
            **_pick_fields(ExecutionPlan, data),
            "assumptions": _tuple(data.get("assumptions")),
            "metadata": dict(data.get("metadata", {})),
        }
    )


def _prediction_plan_from_dict(data: dict[str, Any]) -> PredictionPlan:
    return PredictionPlan(
        **{
            **_pick_fields(PredictionPlan, data),
            "assumptions": _tuple(data.get("assumptions")),
            "metadata": dict(data.get("metadata", {})),
        }
    )


def _predicted_transition_from_dict(data: dict[str, Any]) -> PredictedTransition:
    return PredictedTransition(
        **{
            **_pick_fields(PredictedTransition, data),
            "assumptions": _tuple(data.get("assumptions")),
            "metadata": dict(data.get("metadata", {})),
        }
    )


def _action_result_from_dict(data: dict[str, Any]) -> ActionResult:
    return ActionResult(
        **{
            **_pick_fields(ActionResult, data),
            "artifacts": _tuple(data.get("artifacts")),
            "raw_outputs": _tuple(data.get("raw_outputs")),
            "logs": _tuple(data.get("logs")),
            "errors": _tuple(data.get("errors")),
            "metadata": dict(data.get("metadata", {})),
        }
    )


def _derived_record_from_dict(data: dict[str, Any]) -> DerivedRecord:
    return DerivedRecord(
        **{
            **_pick_fields(DerivedRecord, data),
            "metadata": dict(data.get("metadata", {})),
        }
    )


def _trace_cut_from_dict(data: dict[str, Any]) -> TraceCut:
    return TraceCut(
        **{
            **_pick_fields(TraceCut, data),
            "metadata": dict(data.get("metadata", {})),
        }
    )


def _prediction_match_from_dict(data: dict[str, Any] | None) -> PredictionMatch | None:
    if data is None:
        return None
    return PredictionMatch(**_pick_fields(PredictionMatch, data))


def _observed_transition_from_dict(data: dict[str, Any]) -> ObservedTransition:
    return ObservedTransition(
        transition_id=data["transition_id"],
        transition_kind=data["transition_kind"],
        execution_plan_id=data["execution_plan_id"],
        from_observed_state_id=data["from_observed_state_id"],
        to_observed_state_id=data["to_observed_state_id"],
        action_result=_action_result_from_dict(data["action_result"]),
        matched_predicted_transition_id=data.get("matched_predicted_transition_id"),
        prediction_match=_prediction_match_from_dict(data.get("prediction_match")),
        derived_records=tuple(
            _derived_record_from_dict(item) for item in data.get("derived_records", ())
        ),
        metadata=dict(data.get("metadata", {})),
    )
