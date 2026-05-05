"""§6 Rollout: Horizon vs Branching — virtual future expansion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

from optagent.v2.state import Action, State


@dataclass
class RolloutBudget:
    """Budget for rollout simulation."""
    max_total_cost: float = 100.0
    max_depth: int = 3
    max_branching_per_node: int = 3
    pruning: Any = None


@dataclass
class FuturePath:
    """One possible future path."""
    actions: List[Action] = field(default_factory=list)
    expected_value: float = 0.0
    expected_cost: float = 0.0


@dataclass
class RolloutResult:
    """Result of rollout simulation."""
    paths: List[FuturePath] = field(default_factory=list)
    best_path: FuturePath | None = None
    expected_value: float = 0.0
    expected_cost: float = 0.0
    confidence: float = 0.0


class RolloutSimulator:
    """Simulate future paths from current state."""

    def __init__(self, value_predictor=None):
        self.value_predictor = value_predictor

    def simulate(self, state: State, action: Action, depth: int, budget: RolloutBudget) -> RolloutResult:
        paths = []
        total_cost = 0.0
        
        # Simulate one path with the given action
        path_actions = [action]
        path_value = self._estimate_value(state, action)
        path_cost = action.cost(state)
        
        current_state = state
        for d in range(depth - 1):
            if total_cost + path_cost >= budget.max_total_cost:
                break
            
            # Generate next actions (simplified: use same action type)
            next_action = self._generate_next_action(current_state, action)
            if next_action is None:
                break
                
            path_actions.append(next_action)
            path_value += self._estimate_value(current_state, next_action) * (0.9 ** (d + 1))
            path_cost += next_action.cost(current_state)
            
        paths.append(FuturePath(
            actions=path_actions,
            expected_value=path_value,
            expected_cost=path_cost,
        ))
        
        best = max(paths, key=lambda p: p.expected_value) if paths else None
        
        return RolloutResult(
            paths=paths,
            best_path=best,
            expected_value=best.expected_value if best else 0.0,
            expected_cost=best.expected_cost if best else 0.0,
            confidence=min(1.0, len(paths) / max(budget.max_branching_per_node, 1)),
        )

    def _estimate_value(self, state: State, action: Action) -> float:
        if self.value_predictor:
            return self.value_predictor.predict(action, state)
        return 0.5

    def _generate_next_action(self, state: State, prev_action: Action) -> Action | None:
        # Simplified: return same action type with modified ID
        from optagent.v2.action import ApplyHypothesis
        if isinstance(prev_action, ApplyHypothesis):
            return ApplyHypothesis(
                hypothesis_id=f"{prev_action.hypothesis_id}_next",
                hypothesis_content=prev_action.hypothesis_content,
            )
        return None
