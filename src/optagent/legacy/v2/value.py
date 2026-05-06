"""§9 Value Predictor — lightweight hypothesis value prediction.

Corresponds to PLANNING_AND_RL.md §9.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional
import math

from optagent.legacy.v2.state import Artifact, State
from optagent.legacy.v2.reward import Objective
from optagent.legacy.v2.pareto import euclidean_distance, hypervolume_gain_2d


@dataclass
class ValueFeatures:
    """Grounded features for value prediction (§9.2)."""
    distance_to_pareto_winners: float = 0.0
    expected_hypervolume_gain: float = 0.0
    constraint_violation_probability: float = 0.0
    expected_cost: float = 0.0
    novelty_score: float = 0.0


class ValuePredictor:
    """Predict value of an action before full evaluation."""

    def __init__(self, weights: Optional[dict[str, float]] = None, objectives: List[Objective] = None):
        """Initialize with configurable feature weights (default: equal)."""
        if weights is None:
            weights = {
                "distance_to_pareto_winners": 0.2,
                "expected_hypervolume_gain": 0.3,
                "constraint_violation_probability": 0.2,
                "expected_cost": 0.15,
                "novelty_score": 0.15,
            }
        self.weights = weights
        self.objectives = objectives or []

    def predict(self, action: Any, state: State) -> float:
        features = self._extract_features(action, state)
        return self._score(features)

    def _extract_features(self, action: Any, state: State) -> ValueFeatures:
        """Extract v2 grounded features from state and action."""
        # 1. distance_to_pareto_winners: distance to nearest artifact in pareto_front
        distance_to_pareto = self._compute_distance_to_pareto(action, state)

        # 2. expected_hypervolume_gain: EHI against pareto_front
        hypervolume_gain = self._compute_hypervolume_gain(action, state)

        # 3. constraint_violation_probability: from invariants + failure rate
        constraint_prob = self._compute_constraint_violation_probability(action, state)

        # 4. expected_cost: from action.cost()
        expected_cost = action.cost(state)

        # 5. novelty_score: distance from nearest action in trajectory
        novelty = self._compute_novelty(action, state)

        return ValueFeatures(
            distance_to_pareto_winners=distance_to_pareto,
            expected_hypervolume_gain=hypervolume_gain,
            constraint_violation_probability=constraint_prob,
            expected_cost=expected_cost,
            novelty_score=novelty,
        )

    def _compute_distance_to_pareto(self, action: Any, state: State) -> float:
        """Compute normalized Euclidean distance to nearest Pareto member.

        Returns distance normalized by front diameter (max pairwise distance).
        """
        if not state.artifact.pareto_front:
            return 0.5  # Neutral if no pareto front

        # Synthesize candidate metrics by applying the action
        try:
            candidate_artifact = action.apply(state)
            candidate_metrics = candidate_artifact.metadata.get("metrics")
        except:
            return 0.5

        if not candidate_metrics:
            # Candidate has no metrics; compute using action's content instead
            candidate_metrics = {"action_id": str(action)}

        # Get metric names from objectives
        metric_names = [obj.name for obj in self.objectives]
        if not metric_names:
            # Fallback: use metrics from first front member
            if state.artifact.pareto_front:
                front_metrics = state.artifact.pareto_front[0].metadata.get("metrics", {})
                metric_names = list(front_metrics.keys())

        if not metric_names:
            return 0.5

        # Find nearest front member
        min_distance = float('inf')
        for artifact in state.artifact.pareto_front:
            front_metrics = artifact.metadata.get("metrics", {})
            if not front_metrics:
                continue

            dist = euclidean_distance(candidate_metrics, front_metrics, metric_names)
            min_distance = min(min_distance, dist)

        if min_distance == float('inf'):
            return 0.5

        # Normalize by front diameter (max pairwise distance)
        diameter = 0.0
        for i, art1 in enumerate(state.artifact.pareto_front):
            for art2 in state.artifact.pareto_front[i+1:]:
                m1 = art1.metadata.get("metrics", {})
                m2 = art2.metadata.get("metrics", {})
                if m1 and m2:
                    dist = euclidean_distance(m1, m2, metric_names)
                    diameter = max(diameter, dist)

        if diameter > 0:
            return min(1.0, min_distance / diameter)
        else:
            # All front members equal; no variation
            return 1.0 if min_distance > 0 else 0.0

    def _compute_hypervolume_gain(self, action: Any, state: State) -> float:
        """Compute expected hypervolume improvement against pareto_front."""
        if not state.artifact.pareto_front:
            return 0.8  # High potential if no front exists

        try:
            candidate_artifact = action.apply(state)
        except:
            return 0.5

        # Derive reference point from objectives and current front
        reference_point = {}
        for obj in self.objectives:
            if obj.reference is not None:
                reference_point[obj.name] = obj.reference
            else:
                # Use worst value from front
                vals = [
                    art.metadata.get("metrics", {}).get(obj.name)
                    for art in state.artifact.pareto_front
                    if obj.name in art.metadata.get("metrics", {})
                ]
                if vals:
                    reference_point[obj.name] = max(vals) if obj.direction == "minimize" else min(vals)
                else:
                    reference_point[obj.name] = 0.0

        # Compute hypervolume gain
        if self.objectives:
            gain = hypervolume_gain_2d(
                state.artifact.pareto_front,
                candidate_artifact,
                self.objectives,
                reference_point=reference_point,
            )
            return min(1.0, gain)
        else:
            return 0.5

    def _compute_constraint_violation_probability(self, action: Any, state: State) -> float:
        """Estimate probability of constraint violation from invariants + history."""
        if not state.knowledge.invariants:
            return 0.1  # Default low violation risk

        # Count recent failures in trajectory
        if not state.trajectory:
            return 0.3

        # Simple heuristic: fraction of recent steps with failed constraints
        recent_failures = sum(
            1 for t in state.trajectory[-5:]
            if not t.reward_contribution or all(v <= 0 for v in t.reward_contribution.values())
        )
        return recent_failures / max(len(state.trajectory[-5:]), 1)

    def _compute_novelty(self, action: Any, state: State) -> float:
        """Distance from action to nearest action in trajectory."""
        if not state.trajectory:
            return 1.0  # Fully novel if no history

        # Simplified: assume actions are hashable; count unique
        trajectory_actions = [str(t.action) for t in state.trajectory if t.action]
        action_str = str(action)

        if action_str in trajectory_actions:
            return 0.0  # Seen before, not novel

        return min(1.0, 1.0 / (1.0 + len(trajectory_actions)))

    def _score(self, features: ValueFeatures) -> float:
        """Combine features via configurable weights."""
        # Normalize costs: invert so higher is better (lower cost → higher value)
        cost_penalty = 1.0 / (1.0 + features.expected_cost)

        # Normalize constraint: invert so higher is better (lower violation prob → higher value)
        constraint_bonus = 1.0 - features.constraint_violation_probability

        score = (
            self.weights.get("distance_to_pareto_winners", 0.2) * features.distance_to_pareto_winners +
            self.weights.get("expected_hypervolume_gain", 0.3) * features.expected_hypervolume_gain +
            self.weights.get("constraint_violation_probability", 0.2) * constraint_bonus +
            self.weights.get("expected_cost", 0.15) * cost_penalty +
            self.weights.get("novelty_score", 0.15) * features.novelty_score
        )
        return max(0.0, min(1.0, score))  # Clamp to [0, 1]
