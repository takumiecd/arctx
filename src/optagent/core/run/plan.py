"""RunHandle.plan implementation."""

from __future__ import annotations

from optagent.core.schema.plans import ExecutionPlan, PredictionPlan
from optagent.core.types import JSONValue


def plan_impl(
    self,
    state_id: str,
    *,
    planner: str | None = None,
    max_plans: int | None = None,
    action_type: str = "analysis",
    intent: str | None = None,
    inputs: dict[str, JSONValue] | None = None,
) -> list[ExecutionPlan | PredictionPlan]:
    """Create executable or predictive plans from the given state."""

    count = max(1, max_plans or 1)
    plans: list[ExecutionPlan | PredictionPlan] = []
    for index in range(count):
        if state_id in self.trace_dag.nodes:
            plan = ExecutionPlan(
                plan_id=self._next_id("p_exec"),
                plan_kind="execution",
                from_observed_state_id=state_id,
                action_type=action_type,
                intent=intent or "inspect current state and propose next useful action",
                inputs=dict(inputs or {}),
                metadata={
                    "planner": planner or "default",
                    "ordinal": index,
                },
            )
            self.trace_dag.add_execution_plan(plan)
        elif state_id in self.prediction_dag.nodes:
            plan = PredictionPlan(
                plan_id=self._next_id("p_pred"),
                plan_kind="prediction",
                from_predicted_state_id=state_id,
                action_type=action_type,
                intent=intent or "inspect predicted state and extend the future scenario",
                inputs=dict(inputs or {}),
                metadata={
                    "planner": planner or "default",
                    "ordinal": index,
                },
            )
            self.prediction_dag.add_plan(plan)
        else:
            raise KeyError(f"unknown state_id: {state_id}")
        plans.append(plan)
    return plans
