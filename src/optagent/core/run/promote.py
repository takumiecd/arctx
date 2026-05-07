"""RunHandle.promote implementation."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from optagent.core.schema.derived import DerivedRecord
from optagent.core.schema.plans import ExecutionPlan, PredictionPlan
from optagent.core.schema.results import ActionResult
from optagent.core.schema.state import StateNode
from optagent.core.schema.transitions import (
    ObservedTransition,
    PredictionMatch,
    PredictionPath,
)


def promote_impl(
    self,
    *,
    mode: Literal["plan", "transition"],
    prediction_plan_id: str | None = None,
    prediction_path: PredictionPath | None = None,
    to_observed_state_id: str | None = None,
    predicted_transition_id: str | None = None,
    action_result: ActionResult | None = None,
    execution_plan_id: str | None = None,
    derived_records: list[DerivedRecord] | None = None,
    user_id: str | None = None,
) -> list[ExecutionPlan] | ObservedTransition:
    """Promote prediction-side records into trace-side grounded records."""

    if mode == "plan":
        if to_observed_state_id is None:
            raise ValueError("promote(mode='plan') requires to_observed_state_id")
        return _promote_plan(
            self,
            prediction_plan_id,
            prediction_path,
            to_observed_state_id,
            user_id=user_id,
        )
    if mode == "transition":
        if predicted_transition_id is None or action_result is None:
            raise ValueError(
                "promote(mode='transition') requires predicted_transition_id and action_result"
            )
        return _promote_transition(
            self,
            predicted_transition_id=predicted_transition_id,
            action_result=action_result,
            execution_plan_id=execution_plan_id,
            derived_records=derived_records or [],
            user_id=user_id,
        )
    raise ValueError(f"unsupported promote mode: {mode}")


def _promote_plan(
    self,
    prediction_plan_id: str | None,
    prediction_path: PredictionPath | None,
    to_observed_state_id: str,
    *,
    user_id: str | None = None,
) -> list[ExecutionPlan]:
    self._ensure_active_observed_state(to_observed_state_id)

    plan_ids: list[str] = []
    selected_by_plan: dict[str, str] = {}
    source_path_id: str | None = None
    if prediction_path is not None:
        source_path_id = prediction_path.path_id
        for step in prediction_path.steps:
            plan_ids.append(step.prediction_plan_id)
            selected_by_plan[step.prediction_plan_id] = step.selected_predicted_transition_id
    if prediction_plan_id is not None:
        plan_ids.append(prediction_plan_id)
    if not plan_ids:
        raise ValueError("promote(mode='plan') requires prediction_plan_id or prediction_path")

    promoted: list[ExecutionPlan] = []
    for plan_id in plan_ids:
        source_plan = self.prediction_dag.plans.get(plan_id)
        if not isinstance(source_plan, PredictionPlan):
            raise KeyError(f"unknown prediction_plan_id: {plan_id}")
        execution_plan = ExecutionPlan(
            plan_id=self._next_id("p_exec"),
            plan_kind="execution",
            from_observed_state_id=to_observed_state_id,
            action_type=source_plan.action_type,
            intent=source_plan.intent,
            inputs=dict(source_plan.inputs),
            safety_policy=dict(source_plan.safety_policy),
            assumptions=tuple(source_plan.assumptions),
            metadata={
                **source_plan.metadata,
                "source_prediction_plan_id": source_plan.plan_id,
                "source_prediction_path_id": source_path_id,
                "selected_predicted_transition_id": selected_by_plan.get(plan_id),
                "promotion_id": self._next_id("promotion"),
                **({"user_id": user_id} if user_id is not None else {}),
            },
        )
        self.trace_dag.add_execution_plan(execution_plan)
        promoted.append(execution_plan)
    return promoted


def _promote_transition(
    self,
    *,
    predicted_transition_id: str,
    action_result: ActionResult,
    execution_plan_id: str | None,
    derived_records: list[DerivedRecord],
    user_id: str | None,
) -> ObservedTransition:
    predicted_transition = self.prediction_dag.transitions.get(predicted_transition_id)
    if predicted_transition is None:
        raise KeyError(f"unknown predicted_transition_id: {predicted_transition_id}")
    if execution_plan_id is None:
        raise ValueError("promote(mode='transition') requires execution_plan_id")
        action_result = replace(
            action_result,
            execution_plan_id=execution_plan.plan_id,
        )
    else:
        execution_plan = self.trace_dag.execution_plans.get(execution_plan_id)
        if execution_plan is None:
            raise KeyError(f"unknown execution_plan_id: {execution_plan_id}")
    if action_result.execution_plan_id != execution_plan.plan_id:
        raise ValueError("ActionResult.execution_plan_id must match the ExecutionPlan")
    return _append_observed_transition(
        self,
        plan=execution_plan,
        action_result=action_result,
        matched_predicted_transition_id=predicted_transition.transition_id,
        prediction_match=PredictionMatch(
            matched_predicted_transition_id=predicted_transition.transition_id,
            match_status="compatible",
            prediction_error={},
        ),
        derived_records=derived_records,
        user_id=user_id,
    )


def _append_observed_transition(
    self,
    *,
    plan: ExecutionPlan,
    action_result: ActionResult,
    matched_predicted_transition_id: str | None,
    prediction_match: PredictionMatch | None,
    derived_records: list[DerivedRecord],
    user_id: str | None = None,
) -> ObservedTransition:
    # Reject any plan whose source state has been cut. Plans created
    # before a rewind can still be looked up by id, but the branch
    # they belong to is no longer active.
    self._ensure_active_observed_state(plan.from_observed_state_id)
    next_state = StateNode(
        state_id=self._next_id("s_obs"),
        state_kind="observed",
        snapshot=self.trace_dag.nodes[plan.from_observed_state_id].snapshot,
        snapshot_hash=self.trace_dag.nodes[plan.from_observed_state_id].snapshot_hash,
    )
    next_depth = self.trace_dag.node_depths.get(plan.from_observed_state_id, 0) + 1
    self.trace_dag.add_node(next_state, depth=next_depth)
    transition = ObservedTransition(
        transition_id=self._next_id("t_obs"),
        transition_kind="observed",
        execution_plan_id=plan.plan_id,
        from_observed_state_id=plan.from_observed_state_id,
        to_observed_state_id=next_state.state_id,
        action_result=action_result,
        matched_predicted_transition_id=matched_predicted_transition_id,
        prediction_match=prediction_match,
        derived_records=tuple(derived_records),
        metadata={"user_id": user_id} if user_id is not None else {},
    )
    self.trace_dag.append_transition(transition)
    return transition
