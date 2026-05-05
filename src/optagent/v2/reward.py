"""§4 Reward Spec — multi-objective, constrained, cost-aware."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


@dataclass
class Objective:
    """Single objective definition."""
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
    """Base class for objective-vector scalarization."""

    def aggregate(self, objectives: dict[str, float]) -> float:
        raise NotImplementedError


class WeightedSum(Aggregator):
    """Weighted sum aggregator."""

    def __init__(self, weights: dict[str, float]):
        self.weights = weights

    def aggregate(self, objectives: dict[str, float]) -> float:
        return sum(objectives.get(k, 0.0) * w for k, w in self.weights.items())


class Lexicographic(Aggregator):
    """Lexicographic aggregator: prioritize objectives in strict order."""

    def __init__(self, order: list[str]):
        self.order = order

    def aggregate(self, objectives: dict[str, float]) -> float:
        return tuple(objectives.get(k, float('inf')) for k in self.order)


class Tchebycheff(Aggregator):
    """Tchebycheff aggregator for even Pareto coverage."""

    def __init__(self, reference: dict[str, float], weights: dict[str, float]):
        self.reference = reference
        self.weights = weights

    def aggregate(self, objectives: dict[str, float]) -> float:
        return max(
            self.weights.get(k, 1.0) * abs(objectives.get(k, 0.0) - self.reference.get(k, 0.0))
            for k in set(objectives) | set(self.reference)
        )


@dataclass
class RewardSpec:
    """Structured reward specification."""
    objectives: list[Objective] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    aggregator: Aggregator = field(default_factory=lambda: WeightedSum({}))
    cost_model: CostModel = field(default_factory=CostModel)

    def evaluate(self, metrics: dict[str, float]) -> dict[str, float]:
        """Evaluate metrics against objectives and constraints."""
        results = {}
        for obj in self.objectives:
            if obj.name in metrics:
                results[obj.name] = obj.compute_improvement(metrics[obj.name])
        return results
