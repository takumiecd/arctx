"""§4 Reward Spec — multi-objective, constrained, cost-aware.

Corresponds to PLANNING_AND_RL.md §4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Tuple


@dataclass
class Objective:
    """Single objective definition (§4.2)."""
    name: str
    direction: Literal["minimize", "maximize"]
    normalizer: Callable[[float], float] = field(default_factory=lambda: lambda x: x)
    reference: float | None = None

    def compute_improvement(self, value: float) -> float:
        """Compute improvement ratio over reference."""
        if self.reference is None or self.reference == 0:
            return 1.0
        if self.direction == "minimize":
            return self.reference / value if value > 0 else float('inf')
        else:  # maximize
            return value / self.reference if self.reference > 0 else float('inf')


@dataclass
class Constraint:
    """Hard or soft constraint."""
    predicate: Callable[[Any, Any], bool]
    kind: Literal["hard", "soft"]
    penalty: float = 0.0

    def check(self, state: Any, observation: Any) -> bool:
        return self.predicate(state, observation)


@dataclass
class CostModel:
    """Cost accounting for cost-aware search."""
    units: Literal["wallclock_s", "dollars", "evaluations"] = "wallclock_s"
    accumulator: Callable[[list[float]], float] = field(default_factory=lambda: sum)

    def total_cost(self, costs: list[float]) -> float:
        return self.accumulator(costs)


class Aggregator:
    """Base class for objective-vector scalarization (§4.4).

    Return type is Comparable: either float or Tuple[float, ...] for lexicographic.
    """

    def aggregate(self, objectives: dict[str, float]) -> Any:  # Comparable
        raise NotImplementedError


class WeightedSum(Aggregator):
    """Weighted sum aggregator (§4.4).

    Honors objective direction (minimize → flip sign) and normalizer.
    """

    def __init__(self, weights: dict[str, float] = None, objectives_list: list[Objective] = None):
        self.weights = weights or {}
        self.objectives_list = objectives_list or []  # For direction/normalizer lookup

    def aggregate(self, objectives: dict[str, float]) -> float:
        score = 0.0
        for obj_name, value in objectives.items():
            weight = self.weights.get(obj_name, 1.0)

            # Find objective definition for direction and normalizer
            obj_def = next((o for o in self.objectives_list if o.name == obj_name), None)

            if obj_def:
                # Apply normalizer
                normalized = obj_def.normalizer(value)
                # Flip sign for minimize
                if obj_def.direction == "minimize":
                    normalized = -normalized
            else:
                normalized = value

            score += normalized * weight

        return score


class Lexicographic(Aggregator):
    """Lexicographic aggregator: prioritize objectives in strict order (§4.4).

    Returns Tuple[float, ...] representing the lexicographic ordering.
    """

    def __init__(self, order: list[str]):
        self.order = order

    def aggregate(self, objectives: dict[str, float]) -> Tuple[float, ...]:
        return tuple(objectives.get(k, float('inf')) for k in self.order)


class Tchebycheff(Aggregator):
    """Tchebycheff aggregator for even Pareto coverage (§4.4)."""

    def __init__(self, reference: dict[str, float], weights: dict[str, float] = None):
        self.reference = reference
        self.weights = weights or {}

    def aggregate(self, objectives: dict[str, float]) -> float:
        return max(
            self.weights.get(k, 1.0) * abs(objectives.get(k, 0.0) - self.reference.get(k, 0.0))
            for k in set(objectives) | set(self.reference)
        ) if (set(objectives) | set(self.reference)) else 0.0


class ExpectedHypervolumeImprovement(Aggregator):
    """Expected hypervolume improvement aggregator (§4.4, §9.2).

    For 2D: compute exactly as sum of rectangles.
    For n-D: approximate via Monte-Carlo sampling.
    """

    def __init__(self, reference_point: dict[str, float] = None):
        self.reference_point = reference_point or {}
        self._front: list = []
        self._objectives: list = []

    def update_front(self, front: list, objectives: list) -> None:
        """Update the active Pareto front and objectives."""
        self._front = front
        self._objectives = objectives

    def aggregate(self, objectives: dict[str, float]) -> float:
        """Return EHVI as a scalar (higher = better improvement)."""
        from optagent.legacy.v2.pareto import hypervolume_gain_2d
        from optagent.legacy.v2.state import Artifact

        if not self._objectives:
            return 0.5  # Neutral if no objectives

        # Derive reference point if not explicitly set
        reference_point = self.reference_point.copy() if self.reference_point else {}
        if not reference_point and self._front:
            for obj in self._objectives:
                vals = [
                    art.metadata.get("metrics", {}).get(obj.name)
                    for art in self._front
                    if obj.name in art.metadata.get("metrics", {})
                ]
                if vals:
                    reference_point[obj.name] = max(vals) if obj.direction == "minimize" else min(vals)
                else:
                    reference_point[obj.name] = 0.0

        # Build a transient Artifact from the metrics dict
        candidate = Artifact(
            artifact_id="__ehvi_candidate__",
            content=None,
            metadata={"metrics": objectives},
        )

        gain = hypervolume_gain_2d(
            self._front,
            candidate,
            self._objectives,
            reference_point or None,
        )
        return min(gain, 1.0)


class ConstrainedScalar(Aggregator):
    """Constrained scalar aggregator: primary objective + others as thresholds (§4.4)."""

    def __init__(self, primary_objective: str, constraints: dict[str, float] = None):
        self.primary_objective = primary_objective
        self.constraints = constraints or {}

    def aggregate(self, objectives: dict[str, float]) -> float:
        """Return primary objective if all constraints satisfied, else 0."""
        # Check constraints
        for constraint_name, threshold in self.constraints.items():
            if constraint_name in objectives:
                if objectives[constraint_name] < threshold:
                    return 0.0  # Constraint violated

        # Return primary objective
        return objectives.get(self.primary_objective, 0.0)


@dataclass
class RewardEvaluation:
    """Complete reward evaluation (§4.6, §8.4)."""
    per_objective: dict[str, float]  # Per-objective scores
    constraint_violations: list[str] = field(default_factory=list)  # Hard constraint names violated
    soft_penalty_sum: float = 0.0  # Sum of soft constraint penalties
    aggregated_scalar: float = 0.0  # Final scalar from aggregator
    cost: float = 0.0  # Cost of the action


@dataclass
class RewardSpec:
    """Structured reward specification (§4, §4.6)."""
    objectives: list[Objective] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    aggregator: Aggregator = field(default_factory=lambda: WeightedSum({}))
    cost_model: CostModel = field(default_factory=CostModel)

    def evaluate(self, state: Any, observation: Any) -> RewardEvaluation:
        """Evaluate observation against spec, returning complete RewardEvaluation (§8.4).

        Args:
            state: Current State
            observation: Observation from action execution

        Returns:
            RewardEvaluation with per-objective scores, constraint violations, and aggregated value
        """
        # Compute per-objective improvements
        per_objective = {}
        for obj in self.objectives:
            if obj.name in observation.metrics:
                value = observation.metrics[obj.name]
                # Apply objective direction and normalizer
                normalized = obj.normalizer(value)
                if obj.direction == "minimize":
                    # Flip sign for minimize so higher is better
                    improved = -normalized if normalized != float('inf') else float('-inf')
                else:  # maximize
                    improved = normalized
                per_objective[obj.name] = improved

        # Check constraints
        constraint_violations = []
        soft_penalty_sum = 0.0
        for constraint in self.constraints:
            if not constraint.check(state, observation):
                if constraint.kind == "hard":
                    constraint_violations.append(constraint)
                else:  # soft
                    soft_penalty_sum += constraint.penalty

        # Aggregate to scalar
        aggregated = self.aggregator.aggregate(per_objective)
        if isinstance(aggregated, tuple):
            # Lexicographic: convert to scalar for this evaluation
            aggregated = aggregated[0] if aggregated else 0.0

        # Apply constraint penalties
        if constraint_violations:
            aggregated = 0.0  # Hard violation invalidates result
        aggregated -= soft_penalty_sum

        # Get cost from observation or state
        cost = observation.metadata.get("cost", 0.0) if observation.metadata else 0.0

        return RewardEvaluation(
            per_objective=per_objective,
            constraint_violations=constraint_violations,
            soft_penalty_sum=soft_penalty_sum,
            aggregated_scalar=max(0.0, aggregated),
            cost=cost,
        )
