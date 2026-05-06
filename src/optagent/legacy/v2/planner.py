"""§5 Planner & Replanning — plan as predicted trajectory.

Corresponds to PLANNING_AND_RL.md §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol, Tuple, Callable

from optagent.legacy.v2.state import Observation, State
from optagent.legacy.v2.reward import RewardSpec


@dataclass
class PlannedStep:
    """One step in a plan (§5.1)."""
    action: Any  # Action protocol
    expected_observation: Observation
    expected_state_delta: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    action_subspace: Optional[Callable[[Any], bool]] = None  # §10.2: predicate(Action)->bool


@dataclass
class Plan:
    """Predicted trajectory through state space (§5.1)."""
    steps: List[PlannedStep] = field(default_factory=list)
    expected_terminal_state: Optional[State] = None
    confidence: float = 0.0
    assumptions: List[Any] = field(default_factory=list)
    fallbacks: List["Plan"] = field(default_factory=list)
    posture: str = "guided"  # §10.3: "strict" | "guided" | "open"

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

    def step(self, state: State, plan: Plan) -> Tuple[Any, Plan]:
        ...

    def update(self, state: State, plan: Plan, observation: Observation) -> Plan:
        ...


class DefaultPlanner:
    """Simple planner: generate actions, rank by value, chain into linear plan (§5)."""

    def __init__(self, proposer, value_predictor=None, reward_spec: RewardSpec = None):
        self.proposer = proposer
        self.value_predictor = value_predictor
        self.reward_spec = reward_spec

    def create_plan(self, state: State, reward_spec: RewardSpec, horizon: int) -> Plan:
        """Create plan by generating and ranking actions (§5.1)."""
        self.reward_spec = reward_spec  # Store for replanning

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

    def step(self, state: State, plan: Plan) -> Tuple[Any, Plan]:
        return plan.next_step()

    def update(self, state: State, plan: Plan, observation: Observation) -> Plan:
        """Check replan triggers and update plan (§5.2)."""
        # Check deviation trigger
        if plan.steps:
            expected = plan.steps[0].expected_observation
            if expected and observation:
                # Read calibration threshold from state.knowledge
                deviation = self._compute_deviation(expected, observation, state)
                if deviation > self._get_deviation_threshold(state):
                    # Trigger replan
                    return self._replan(state, plan)

        return plan

    def _compute_deviation(
        self,
        expected: Observation,
        actual: Observation,
        state: State,
    ) -> float:
        """Compute deviation between expected and actual observation (§5.2)."""
        if not expected.metrics or not actual.metrics:
            return 0.0
        diffs = []
        for k in expected.metrics:
            if k in actual.metrics:
                diffs.append(abs(expected.metrics[k] - actual.metrics[k]))
        return sum(diffs) / len(diffs) if diffs else 0.0

    def _get_deviation_threshold(self, state: State) -> float:
        """Read deviation threshold from calibration data (§5.2).

        Default: k=2, so threshold = 2 * sigma_noise.
        Fall back to 0.5 if no calibration.
        """
        if state.knowledge.calibration:
            sigma = state.knowledge.calibration.get("noise_std", 0.25)
            return 2.0 * sigma
        return 0.5  # Fallback

    def _replan(self, state: State, plan: Plan) -> Plan:
        """Trigger replan from current state (§5.2)."""
        if plan.fallbacks:
            return plan.fallbacks[0]

        # Actually replan from current state with remaining horizon
        if self.reward_spec is None:
            return Plan()  # No reward spec, can't replan

        remaining_horizon = len(plan.steps)
        if remaining_horizon <= 0:
            return Plan()

        # Generate fresh plan from current state
        return self.create_plan(state, self.reward_spec, horizon=remaining_horizon)
