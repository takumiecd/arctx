"""RunHandle.observe implementation."""

from __future__ import annotations

from optagent.core.schema.derived import DerivedRecord
from optagent.core.schema.results import ActionResult
from optagent.core.schema.transitions import ObservedTransition


def observe_impl(
    self,
    execution_plan_id: str,
    action_result: ActionResult,
    *,
    derived_records: list[DerivedRecord] | None = None,
) -> ObservedTransition:
    """Record an execution result without matching it to a prediction."""

    plan = self.trace_dag.execution_plans.get(execution_plan_id)
    if plan is None:
        raise KeyError(f"unknown execution_plan_id: {execution_plan_id}")
    if action_result.execution_plan_id != execution_plan_id:
        raise ValueError("ActionResult.execution_plan_id must match execution_plan_id")
    return self._append_observed_transition(
        plan=plan,
        action_result=action_result,
        matched_predicted_transition_id=None,
        prediction_match=None,
        derived_records=derived_records or [],
    )
