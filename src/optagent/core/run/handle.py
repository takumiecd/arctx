"""Run handle definition and initialization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from optagent.core.ids import sequential_id, slugify, timestamp_id
from optagent.core.schema.requirements import Requirement
from optagent.core.schema.state import StateNode, StateSnapshot
from optagent.core.dag import PredictionDAG, TraceDAG


def _snapshot_hash(snapshot: StateSnapshot) -> str:
    encoded = json.dumps(snapshot.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class RunHandle:
    """In-memory handle for one optimization/problem-solving run.

    This class implements the canonical API shape without choosing a real
    planner, predictor, executor, or storage backend. Those can be layered on
    top while preserving the source-of-truth records.
    """

    run_id: str
    requirement: Requirement
    trace_dag: TraceDAG
    prediction_dag: PredictionDAG
    current_observed_state_id: str
    _counters: dict[str, int] = field(default_factory=dict)

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return sequential_id(prefix, self._counters[prefix])

    @property
    def current_observed_state(self) -> StateNode:
        return self.trace_dag.nodes[self.current_observed_state_id]

    def save(self, store) -> object:
        """Save this run through a storage adapter."""
        return store.save_run(self)


def init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle:
    """Create a new in-memory run with TraceDAG and PredictionDAG roots."""

    rid = run_id or timestamp_id(f"run_{slugify(requirement.requirement_id)}")
    initial_snapshot = StateSnapshot(requirement=requirement)
    observed = StateNode(
        state_id="s_obs_0000",
        state_kind="observed",
        snapshot=initial_snapshot,
        snapshot_hash=_snapshot_hash(initial_snapshot),
    )
    trace_dag = TraceDAG(dag_id=f"{rid}_trace")
    trace_dag.add_node(observed, depth=0)
    predicted_root = StateNode(
        state_id="s_pred_0000",
        state_kind="predicted",
        snapshot=observed.snapshot,
        snapshot_hash=observed.snapshot_hash,
        anchor_observed_state_id=observed.state_id,
    )
    prediction_dag = PredictionDAG(
        dag_id=f"{rid}_prediction",
        anchor_observed_state_id=observed.state_id,
        root_predicted_state_id=predicted_root.state_id,
    )
    prediction_dag.add_node(predicted_root, depth=0)
    return RunHandle(
        run_id=rid,
        requirement=requirement,
        trace_dag=trace_dag,
        prediction_dag=prediction_dag,
        current_observed_state_id=observed.state_id,
        _counters={
            "s_obs": 0,
            "s_pred": 0,
            "p_exec": 0,
            "p_pred": 0,
            "t_obs": 0,
            "t_pred": 0,
            "sel_pred": 0,
            "promotion": 0,
            "prediction_dag": 0,
        },
    )
