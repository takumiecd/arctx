"""RunHandle.plan and RunHandle.extend implementations."""

from __future__ import annotations

from optagent.core.schema.plans import ExecutionPlan, PredictionPlan
from optagent.core.types import JSONValue


def plan_impl(
    self,
    state_id: str | None = None,
    *,
    planner: str | None = None,
    max_plans: int | None = None,
    action_type: str = "analysis",
    intent: str | None = None,
    inputs: dict[str, JSONValue] | None = None,
) -> list[ExecutionPlan]:
    """Create one or more ``ExecutionPlan``s from an observed state.

    Parameters
    ----------
    state_id:
        Source observed state. Defaults to the current observed state.

    Raises
    ------
    KeyError
        If *state_id* is not an observed state in this run.
    """

    target = state_id or self.current_observed_state_id
    if target not in self.trace_dag.nodes:
        raise KeyError(f"not an observed state: {target}")

    count = max(1, max_plans or 1)
    resolved_intent = intent or "inspect current state and propose next useful action"
    resolved_planner = planner or "default"
    plans: list[ExecutionPlan] = []
    for index in range(count):
        plan = ExecutionPlan(
            plan_id=self._next_id("p_exec"),
            plan_kind="execution",
            from_observed_state_id=target,
            action_type=action_type,
            intent=resolved_intent,
            inputs=dict(inputs or {}),
            metadata={"planner": resolved_planner, "ordinal": index},
        )
        self.trace_dag.add_execution_plan(plan)
        plans.append(plan)
    return plans


def extend_impl(
    self,
    state_id: str,
    *,
    planner: str | None = None,
    max_plans: int | None = None,
    action_type: str = "analysis",
    intent: str | None = None,
    inputs: dict[str, JSONValue] | None = None,
) -> list[PredictionPlan]:
    """Create one or more ``PredictionPlan``s from a predicted state.

    Predicted states have no implicit "current", so *state_id* is required.

    Raises
    ------
    KeyError
        If *state_id* is not a predicted state in this run.
    """

    if state_id not in self.prediction_dag.nodes:
        raise KeyError(f"not a predicted state: {state_id}")

    count = max(1, max_plans or 1)
    resolved_intent = intent or "inspect predicted state and extend the future scenario"
    resolved_planner = planner or "default"
    plans: list[PredictionPlan] = []
    for index in range(count):
        plan = PredictionPlan(
            plan_id=self._next_id("p_pred"),
            plan_kind="prediction",
            from_predicted_state_id=state_id,
            action_type=action_type,
            intent=resolved_intent,
            inputs=dict(inputs or {}),
            metadata={"planner": resolved_planner, "ordinal": index},
        )
        self.prediction_dag.add_plan(plan)
        plans.append(plan)
    return plans
