"""RunHandle helper methods."""

from __future__ import annotations

from optagent.core.plans import ExecutionPlan, PredictionPlan
from optagent.core.state import StateNode


def find_plan_impl(self, plan_id: str) -> ExecutionPlan | PredictionPlan:
    if plan_id in self.trace_dag.execution_plans:
        return self.trace_dag.execution_plans[plan_id]
    if plan_id in self.prediction_dag.plans:
        return self.prediction_dag.plans[plan_id]
    raise KeyError(f"unknown plan_id: {plan_id}")


def plan_from_state_id_impl(self, plan: ExecutionPlan | PredictionPlan) -> str:
    if hasattr(plan, "from_observed_state_id"):
        return plan.from_observed_state_id
    return plan.from_predicted_state_id


def predicted_depth_for_plan_impl(self, plan: ExecutionPlan | PredictionPlan) -> int:
    state_id = plan_from_state_id_impl(self, plan)
    return self.prediction_dag.node_depths.get(state_id, 0)


def make_predicted_state_impl(
    self,
    plan: ExecutionPlan | PredictionPlan,
    outcome_index: int,
) -> StateNode:
    anchor_id = (
        plan.from_observed_state_id
        if hasattr(plan, "from_observed_state_id")
        else self.prediction_dag.anchor_observed_state_id
    )
    anchor = self.trace_dag.nodes[anchor_id]
    return StateNode(
        state_id=self._next_id("s_pred"),
        state_kind="predicted",
        snapshot=anchor.snapshot,
        snapshot_hash=anchor.snapshot_hash,
        anchor_observed_state_id=anchor_id,
        assumptions=tuple(plan.assumptions),
        confidence=getattr(plan, "confidence", None),
        metadata={
            "source_plan_id": plan.plan_id,
            "outcome_index": outcome_index,
        },
    )
