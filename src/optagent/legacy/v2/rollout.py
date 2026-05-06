"""§6 Rollout: Horizon vs Branching — virtual future expansion.

Corresponds to PLANNING_AND_RL.md §6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from optagent.legacy.v2.state import Observation, State
from optagent.legacy.v2.policy import Proposer


@dataclass
class RolloutBudget:
    """Budget for rollout simulation (§6.2)."""
    max_total_cost: float = 100.0
    max_depth: int = 3
    max_branching_per_node: int = 3
    pruning: Any = None


@dataclass
class FuturePath:
    """One possible future path."""
    actions: List[Any] = field(default_factory=list)
    expected_value: float = 0.0
    expected_cost: float = 0.0


@dataclass
class RolloutResult:
    """Result of rollout simulation (§6.3)."""
    paths: List[FuturePath] = field(default_factory=list)
    best_path: Optional[FuturePath] = None
    expected_value: float = 0.0
    expected_cost: float = 0.0
    confidence: float = 0.0


class RolloutSimulator:
    """Simulate future paths from current state with branching and pruning."""

    def __init__(self, proposer: Proposer, value_predictor=None):
        self.proposer = proposer
        self.value_predictor = value_predictor

    def simulate(
        self,
        state: State,
        budget: RolloutBudget,
        depth: int = 0,
    ) -> RolloutResult:
        """Expand rollout tree via branching, respecting budget (§6.2).

        Uses beam search: at each depth level, generates k actions per proposer,
        values them, and expands the top-b paths (beam width = max_branching_per_node).
        """
        if depth >= budget.max_depth:
            return RolloutResult()

        # Start with root state
        paths = [FuturePath(actions=[], expected_value=0.0, expected_cost=0.0)]
        accumulated_cost = 0.0

        for d in range(budget.max_depth):
            new_paths = []
            explored_states = set()

            for path in paths:
                # Get current state by replaying path actions
                current_state = self._replay_path(state, path)

                # Pruning: skip if in ruled_out regions
                if self._is_in_ruled_out_regions(current_state):
                    continue

                # Generate candidate actions via proposer
                actions = self.proposer.generate_actions(
                    current_state,
                    n=budget.max_branching_per_node,
                    temperature=0.7,
                )

                # Score and expand actions
                for action in actions:
                    action_cost = action.cost(current_state)

                    # Cost-bounded pruning
                    if accumulated_cost + action_cost > budget.max_total_cost:
                        continue

                    # Value-based pruning
                    predicted_value = self._estimate_value(current_state, action)
                    if predicted_value < 0.1:  # Skip very low-value paths
                        continue

                    # Create new path
                    new_path = FuturePath(
                        actions=path.actions + [action],
                        expected_value=path.expected_value + predicted_value * (0.95 ** d),
                        expected_cost=path.expected_cost + action_cost,
                    )

                    new_paths.append(new_path)
                    accumulated_cost += action_cost

            # Beam search: keep top-k by value (§6.2)
            if new_paths:
                new_paths.sort(key=lambda p: p.expected_value, reverse=True)
                paths = new_paths[: budget.max_branching_per_node]
            else:
                break

        # Compute result
        best = max(paths, key=lambda p: p.expected_value) if paths else None

        return RolloutResult(
            paths=paths,
            best_path=best,
            expected_value=best.expected_value if best else 0.0,
            expected_cost=best.expected_cost if best else 0.0,
            confidence=min(1.0, len(paths) / max(budget.max_branching_per_node, 1)),
        )

    def _replay_path(self, initial_state: State, path: FuturePath) -> State:
        """Replay actions to compute resulting state."""
        current_state = initial_state
        for action in path.actions:
            obs = Observation(action_id=str(action), metrics={})
            current_state = current_state.advance(action, obs)
        return current_state

    def _is_in_ruled_out_regions(self, state: State) -> bool:
        """Check if current state is in any ruled-out region (§6.2 knowledge-pruning)."""
        if not state.knowledge.ruled_out_regions:
            return False
        # Simplified: assume regions are comparable to state somehow
        return False

    def _estimate_value(self, state: State, action: Any) -> float:
        """Estimate value of action via predictor (§9)."""
        if self.value_predictor:
            return self.value_predictor.predict(action, state)
        return 0.5  # Neutral default
