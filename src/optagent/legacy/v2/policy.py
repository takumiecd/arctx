"""§7 Policy: LLM as Stochastic Policy — calibration strategies.

Corresponds to PLANNING_AND_RL.md §7.
"""

from __future__ import annotations

from typing import List, Protocol, Optional, Any
from collections import Counter

from optagent.legacy.v2.state import State


class Proposer(Protocol):
    """Generate and score candidate actions (§7.4)."""

    def generate_actions(self, state: State, n: int, temperature: float) -> List[Any]:
        ...

    def score_actions(self, state: State, actions: List[Any]) -> List[float]:
        ...

    def evaluate_state(self, state: State) -> float:
        """Lightweight value estimate (§7.4)."""
        ...


class LLMProposer:
    """Wrap LLM backend as calibrated proposer (§7.2, §7.3).

    If no backend provided, uses mock generation with empirical frequency calibration.
    TODO: Integrate real LLM backend via .complete(prompt, n, temperature) interface.
    """

    def __init__(self, backend=None, calibration_strategy: str = "n_sample"):
        self.backend = backend
        self.calibration_strategy = calibration_strategy
        self._history = []  # Track generated actions for empirical calibration
        self._action_counts = Counter()  # Count identical actions for frequency

    def generate_actions(self, state: State, n: int, temperature: float) -> List[Any]:
        """Generate candidate actions (§7.2).

        Action IDs are deterministic based on state fingerprint and action index,
        not on call order. This ensures the same state generates the same action IDs.
        """
        if self.backend:
            # Use backend to generate actions
            # TODO: implement actual backend integration
            prompt = f"Generate {n} optimization hypotheses for the current state."
            responses = self.backend.complete(prompt, n=n, temperature=temperature)
            actions = [self._parse_response(r) for r in responses]
        else:
            # Mock: generate actions with stable IDs based on state + index
            from optagent.legacy.v2.action import ApplyHypothesis
            from hashlib import md5

            # Create state fingerprint for deterministic ID generation
            state_repr = repr(sorted(vars(state).items()))
            state_hash = md5(state_repr.encode()).hexdigest()[:8]

            actions = []
            for i in range(n):
                # Action ID is based on state fingerprint and index, not history length
                action = ApplyHypothesis(
                    hypothesis_id=f"h_{state_hash}_{i}",
                    hypothesis_content=f"optimization_{state_hash}_{i}",
                )
                actions.append(action)
            self._history.extend(actions)

        return actions

    def score_actions(self, state: State, actions: List[Any]) -> List[float]:
        """Score actions by empirical frequency or LLM-generated priors (§7.2).

        Empirical strategy: cluster identical actions by string representation,
        count frequencies, and return normalized scores.
        """
        if not actions:
            return []

        if self.calibration_strategy == "n_sample":
            # Empirical frequency calibration
            action_strs = [str(a) for a in actions]

            # Update counts for actions in history
            for a in self._history:
                self._action_counts[str(a)] += 1

            # Compute frequencies
            total = sum(self._action_counts.values())
            if total == 0:
                # No history, uniform distribution
                return [1.0 / len(actions)] * len(actions)

            scores = [self._action_counts[a_str] / total for a_str in action_strs]

            # Normalize
            score_sum = sum(scores)
            if score_sum > 0:
                scores = [s / score_sum for s in scores]
            else:
                # New actions, use uniform
                scores = [1.0 / len(actions)] * len(actions)

            return scores

        elif self.calibration_strategy == "logprob":
            # Mock logprob-based scoring (would use token-level logprobs in practice)
            return [0.5 + i * 0.1 for i in range(len(actions))]

        return [1.0 / len(actions)] * len(actions)

    def evaluate_state(self, state: State) -> float:
        """Lightweight value estimate without full execution (§7.4).

        Simple heuristic: based on trajectory length and past success.
        """
        if not state.trajectory:
            return 0.5

        # Heuristic: higher success rate in trajectory → higher state value
        successes = sum(1 for t in state.trajectory if t.reward_contribution and any(t.reward_contribution.values()))
        success_rate = successes / len(state.trajectory)

        # Decay by trajectory length (deeper states are more uncertain)
        decay = 1.0 / (1.0 + len(state.trajectory) * 0.1)

        return success_rate * decay

    def _parse_response(self, response: str) -> Action:
        """Parse LLM response into an Action (stub).

        TODO: Implement actual parsing based on action domain.
        """
        from optagent.legacy.v2.action import ApplyHypothesis
        return ApplyHypothesis(
            hypothesis_id=f"parsed_{hash(response)}",
            hypothesis_content=response,
        )
