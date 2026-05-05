"""§5 Planner & Replanning — plan as predicted trajectory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol, Tuple

from optagent.v2.state import Action, Observation, State
from optagent.v2.reward import RewardSpec


@dataclass
class PlannedStep:
    """One step in a plan."""
    action: Action
    expected_observation: Observation
    expected_state_delta: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """Predicted trajectory through state space."""
    steps: List[PlannedStep] = field(default_factory=list)
    expected_terminal_state: Optional[State] = None
    confidence: float = 0.0
    assumptions: List[Any] = field(default_factory=list)
    fallbacks: List["Plan"] = field(default_factory=list)

    def is_complete(self) -> bool:
        return len(self.steps) == 0

    def next_step(self) -> Tuple[Action, "Plan"]:
        """Pop and return next action, returning remaining plan."""
        if not self.steps:
            raise StopIteration("Plan is complete")
        step = self.steps[0]
        remaining = Plan(
            steps=self.steps[1:],
            expected_terminal_state=self.expected_terminal_state,
            confidence=self.confidence,
            assumptions=self.assumptions,
            fallbacks=self.fallbacks,
        )
        return step.action, remaining


class Planner(Protocol):
    """Planner Protocol."""

    def create_plan(self, state: State, reward_spec: RewardSpec, horizon: int) -> Plan:
        ...

    def step(self, state: State, plan: Plan) -> Tuple[Action, Plan]:
        ...

    def update(self, state: State, plan: Plan, observation: Observation) -> Plan:
        ...


class DefaultPlanner:
    """Simple planner: generate actions, rank by value, chain into linear plan."""

    def __init__(self, proposer, value_predictor=None):
        self.proposer = proposer
        self.value_predictor = value_predictor

    def create_plan(self, state: State, reward_spec: RewardSpec, horizon: int) -> Plan:
        actions = self.proposer.generate_actions(state, n=10, temperature=0.7)
        
        if self.value_predictor:
            scored = [(a, self.value_predictor.predict(a, state)) for a in actions]
            scored.sort(key=lambda x: x[1], reverse=True)
            actions = [a for a, _ in scored[:horizon]]
        else:
            actions = actions[:horizon]
        
        steps = []
        for action in actions:
            steps.append(PlannedStep(
                action=action,
                expected_observation=Observation(action_id=str(action)),
            ))
        
        return Plan(steps=steps, confidence=0.5)

    def step(self, state: State, plan: Plan) -> Tuple[Action, Plan]:
        return plan.next_step()

    def update(self, state: State, plan: Plan, observation: Observation) -> Plan:
        # Check deviation trigger
        if plan.steps:
            expected = plan.steps[0].expected_observation
            if expected and observation:
                deviation = self._compute_deviation(expected, observation)
                if deviation > 0.5:  # threshold
                    # Trigger replan
                    return self._replan(state, plan)
        return plan

    def _compute_deviation(self, expected: Observation, actual: Observation) -> float:
        if not expected.metrics or not actual.metrics:
            return 0.0
        diffs = []
        for k in expected.metrics:
            if k in actual.metrics:
                diffs.append(abs(expected.metrics[k] - actual.metrics[k]))
        return sum(diffs) / len(diffs) if diffs else 0.0

    def _replan(self, state: State, plan: Plan) -> Plan:
        if plan.fallbacks:
            return plan.fallbacks[0]
        return Plan()  # Empty plan as fallback
