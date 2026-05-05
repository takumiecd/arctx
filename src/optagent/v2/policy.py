"""§7 Policy: LLM as Stochastic Policy — calibration strategies."""

from __future__ import annotations

from typing import List, Protocol

from optagent.v2.state import Action, State


class Proposer(Protocol):
    """Generate and score candidate actions."""

    def generate_actions(self, state: State, n: int, temperature: float) -> List[Action]:
        ...

    def score_actions(self, state: State, actions: List[Action]) -> List[float]:
        ...


class LLMProposer:
    """Wrap LLM backend as calibrated proposer."""

    def __init__(self, backend, calibration_strategy: str = "n_sample"):
        self.backend = backend
        self.calibration_strategy = calibration_strategy
        self._history = []  # Track generated actions for calibration

    def generate_actions(self, state: State, n: int, temperature: float) -> List[Action]:
        actions = []
        for _ in range(n):
            # Mock: generate deterministic actions for now
            from optagent.v2.action import ApplyHypothesis
            actions.append(ApplyHypothesis(
                hypothesis_id=f"h_{len(self._history)}",
                hypothesis_content=f"optimization_{len(self._history)}",
            ))
            self._history.append(actions[-1])
        return actions

    def score_actions(self, state: State, actions: List[Action]) -> List[float]:
        if self.calibration_strategy == "n_sample":
            # Empirical frequency (uniform for now)
            return [1.0 / len(actions)] * len(actions) if actions else []
        elif self.calibration_strategy == "logprob":
            # Mock logprob-based scoring
            return [0.5 + i * 0.1 for i in range(len(actions))] if actions else []
        return [1.0 / len(actions)] * len(actions) if actions else []
