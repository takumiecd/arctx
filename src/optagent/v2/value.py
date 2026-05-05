"""§9 Value Predictor — lightweight hypothesis value prediction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from optagent.v2.state import Action, State


@dataclass
class ValueFeatures:
    """Features for value prediction."""
    similarity_to_past_winners: float = 0.0
    complexity_estimate: float = 0.0
    risk_score: float = 0.0
    expected_validation_success: float = 0.0


class ValuePredictor:
    """Predict value of an action before full evaluation."""

    def predict(self, action: Action, state: State) -> float:
        features = self._extract_features(action, state)
        return self._score(features)

    def _extract_features(self, action: Action, state: State) -> ValueFeatures:
        # Heuristic feature extraction
        trajectory_len = len(state.trajectory)
        past_success = sum(1 for t in state.trajectory if t.reward_contribution)
        
        return ValueFeatures(
            similarity_to_past_winners=past_success / max(trajectory_len, 1),
            complexity_estimate=1.0,  # Default
            risk_score=0.3 if trajectory_len > 0 else 0.5,
            expected_validation_success=0.8 if past_success > 0 else 0.5,
        )

    def _score(self, features: ValueFeatures) -> float:
        # Heuristic scoring
        score = (features.expected_validation_success * 0.4 + 
                 features.similarity_to_past_winners * 0.3 +
                 (1.0 - features.risk_score) * 0.3)
        return score
