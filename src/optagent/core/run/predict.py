"""RunHandle.predict and select_prediction implementations."""

from __future__ import annotations

from optagent.core.schema.state import StateNode
from optagent.core.schema.transitions import (
    PredictionSelection,
    PredictedTransition,
)


def predict_impl(
    self,
    plan_id: str,
    *,
    predictor: str | None = None,
    max_outcomes: int | None = None,
) -> list[PredictedTransition]:
    """Expand the PredictionDAG with predicted outcomes for a plan."""

    plan = self._find_plan(plan_id)
    if hasattr(plan, "plan_kind") and plan.plan_kind == "execution" and plan.plan_id not in self.prediction_dag.plans:
        self.prediction_dag.add_plan(plan)
    count = max(1, max_outcomes or 1)
    transitions: list[PredictedTransition] = []
    for index in range(count):
        predicted_state = self._make_predicted_state(plan, index)
        depth = self._predicted_depth_for_plan(plan) + 1
        self.prediction_dag.add_node(predicted_state, depth=depth)
        transition = PredictedTransition(
            transition_id=self._next_id("t_pred"),
            transition_kind="predicted",
            parent_plan_id=plan.plan_id,
            parent_plan_kind=plan.plan_kind,
            from_state_id=self._plan_from_state_id(plan),
            outcome_id=f"outcome_{index + 1}",
            outcome_label="default predicted outcome",
            predicted_result={
                "status": "unknown",
                "predictor": predictor or "default",
            },
            to_predicted_state_id=predicted_state.state_id,
            metadata={"ordinal": index},
        )
        self.prediction_dag.add_transition(transition)
        transitions.append(transition)
    return transitions


def select_prediction_impl(
    self,
    *,
    predicted_transition_id: str | None = None,
    predicted_transition_ids: list[str] | None = None,
    to_predicted_state_id: str | None = None,
    reason: str = "",
) -> PredictionSelection:
    """Select predicted transitions for later promotion or comparison."""

    selected = list(predicted_transition_ids or ())
    if predicted_transition_id is not None:
        selected.append(predicted_transition_id)
    if to_predicted_state_id is not None:
        selected.extend(
            transition_id
            for transition_id, transition in self.prediction_dag.transitions.items()
            if transition.to_predicted_state_id == to_predicted_state_id
        )
    if not selected:
        raise ValueError("select_prediction requires at least one predicted transition")
    for transition_id in selected:
        if transition_id not in self.prediction_dag.transitions:
            raise KeyError(f"unknown predicted_transition_id: {transition_id}")
    return PredictionSelection(
        selection_id=self._next_id("sel_pred"),
        selected_transition_ids=tuple(dict.fromkeys(selected)),
        reason=reason,
    )
