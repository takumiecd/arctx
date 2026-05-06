"""Prediction and execution plan records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from optagent.core.types import ActionType, JSONValue, PlanStatus, to_jsonable


@dataclass(frozen=True)
class PredictionPlan:
    """Hypothetical plan that only exists inside a PredictionDAG."""

    plan_id: str
    plan_kind: Literal["prediction"]
    from_predicted_state_id: str
    action_type: ActionType
    intent: str
    inputs: dict[str, JSONValue] = field(default_factory=dict)
    expected_observation: dict[str, JSONValue] = field(default_factory=dict)
    expected_state_delta: dict[str, JSONValue] = field(default_factory=dict)
    estimated_cost: dict[str, JSONValue] = field(default_factory=dict)
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    confidence: float | None = None
    status: PlanStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ExecutionPlan:
    """Plan grounded in an observed state and safe to pass to an executor."""

    plan_id: str
    plan_kind: Literal["execution"]
    from_observed_state_id: str
    action_type: ActionType
    intent: str
    inputs: dict[str, JSONValue] = field(default_factory=dict)
    expected_observation: dict[str, JSONValue] = field(default_factory=dict)
    expected_state_delta: dict[str, JSONValue] = field(default_factory=dict)
    estimated_cost: dict[str, JSONValue] = field(default_factory=dict)
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    status: PlanStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
