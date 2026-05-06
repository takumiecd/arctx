"""RunHandle.trace and refresh implementations."""

from __future__ import annotations

from optagent.core.schema.state import StateNode, TraceContext
from optagent.core.tree import PredictionDAG


def trace_impl(
    self,
    state_id: str | None = None,
    *,
    depth: int | None = None,
    include_derived: bool = True,
    include_raw_refs: bool = True,
) -> TraceContext:
    """Walk observed history backwards from a state."""

    current_id = state_id or self.current_observed_state_id
    if current_id not in self.trace_dag.nodes:
        raise KeyError(f"unknown observed state_id: {current_id}")

    remaining = depth
    cursor = current_id
    past_state_ids: list[str] = []
    transition_ids: list[str] = []
    execution_plan_ids: list[str] = []
    result_ids: list[str] = []
    matched_predicted_ids: list[str] = []
    derived_ids: list[str] = []
    artifact_refs: list[str] = []

    while remaining is None or remaining > 0:
        incoming = self.trace_dag.past_transition_ids(cursor)
        if not incoming:
            break
        transition = self.trace_dag.transitions[incoming[-1]]
        transition_ids.append(transition.transition_id)
        execution_plan_ids.append(transition.execution_plan_id)
        result_ids.append(transition.action_result.result_id)
        past_state_ids.append(transition.from_observed_state_id)
        if transition.matched_predicted_transition_id is not None:
            matched_predicted_ids.append(transition.matched_predicted_transition_id)
        if include_derived:
            derived_ids.extend(record.derived_id for record in transition.derived_records)
        if include_raw_refs:
            artifact_refs.extend(transition.action_result.artifacts)
            artifact_refs.extend(transition.action_result.raw_outputs)
            artifact_refs.extend(transition.action_result.logs)
        cursor = transition.from_observed_state_id
        if remaining is not None:
            remaining -= 1

    return TraceContext(
        current_state_id=current_id,
        past_state_ids=tuple(past_state_ids),
        observed_transition_ids=tuple(transition_ids),
        execution_plan_ids=tuple(execution_plan_ids),
        action_result_ids=tuple(result_ids),
        matched_predicted_transition_ids=tuple(matched_predicted_ids),
        derived_record_ids=tuple(derived_ids),
        artifact_refs=tuple(artifact_refs),
    )


def refresh_impl(
    self,
    *,
    from_state_id: str | None = None,
    mode: str = "reset",
) -> PredictionDAG:
    """Re-anchor the PredictionDAG to an observed state."""

    observed_state_id = from_state_id or self.current_observed_state_id
    observed_state = self.trace_dag.nodes.get(observed_state_id)
    if observed_state is None or observed_state.state_kind != "observed":
        raise KeyError(f"unknown observed state_id: {observed_state_id}")
    if mode not in {"reset", "stale"}:
        raise ValueError("refresh mode must be 'reset' or 'stale'")
    if mode == "stale":
        self.prediction_dag.stale = True
    self.prediction_dag = _new_prediction_dag(self, observed_state)
    return self.prediction_dag


def _new_prediction_dag(self, observed_state: StateNode) -> PredictionDAG:
    root = StateNode(
        state_id=self._next_id("s_pred"),
        state_kind="predicted",
        snapshot=observed_state.snapshot,
        snapshot_hash=observed_state.snapshot_hash,
        anchor_observed_state_id=observed_state.state_id,
    )
    dag = PredictionDAG(
        dag_id=self._next_id("prediction_dag"),
        anchor_observed_state_id=observed_state.state_id,
        root_predicted_state_id=root.state_id,
    )
    dag.add_node(root, depth=0)
    return dag
