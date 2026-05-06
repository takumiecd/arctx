"""§3 Action Space — domain-specific action kinds.

Corresponds to PLANNING_AND_RL.md §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from optagent.legacy.v2.state import Artifact, State


class Action(Protocol):
    """§3 Action Protocol — domain-pluggable state transition.

    Actions are first-class units that produce state transitions with cost.
    """

    def apply(self, state: State) -> Artifact:
        """Produce a new candidate artifact (does not yet update knowledge)."""
        ...

    def cost(self, state: State) -> float:
        """Estimated cost of executing this action."""
        ...

    def observability(self) -> dict[str, str]:
        """Declares what will be observed after execution."""
        ...


class CostModel:
    """Simple cost model for state-dependent action costs (§3.3, §14)."""

    def __init__(self, base_cost: float = 1.0, depth_multiplier: float = 0.1):
        self.base_cost = base_cost
        self.depth_multiplier = depth_multiplier

    def compute(self, state: State) -> float:
        """Compute cost based on trajectory depth."""
        depth_penalty = len(state.trajectory) * self.depth_multiplier
        return self.base_cost * (1.0 + depth_penalty)


@dataclass
class ApplyHypothesis:
    """Action: apply an optimization hypothesis to produce a candidate (§3, §11.1)."""
    hypothesis_id: str
    hypothesis_content: str
    cost_model: Optional[CostModel] = None

    def apply(self, state: State) -> Artifact:
        """Produce artifact from hypothesis (§3.1, §13).

        Includes parent_id in metadata to track lineage.
        """
        metadata = {"hypothesis_id": self.hypothesis_id}

        # Track parent incumbent if available (§13)
        if state.artifact.incumbent:
            metadata["parent_artifact_id"] = state.artifact.incumbent.artifact_id

        return Artifact(
            artifact_id=self.hypothesis_id,
            content=self.hypothesis_content,
            metadata=metadata,
        )

    def cost(self, state: State) -> float:
        """Estimate cost of executing this action (§3.3, §14).

        State-dependent: later actions (deeper trajectory) are more expensive.
        """
        if self.cost_model:
            return self.cost_model.compute(state)

        # Default: base cost + depth penalty
        depth_penalty = len(state.trajectory) * 0.1
        return 1.0 * (1.0 + depth_penalty)

    def observability(self) -> dict[str, str]:
        return {"artifact": "candidate_artifact"}


@dataclass
class RunEvaluation:
    """Action: evaluate a candidate artifact (§3, §11.1)."""
    artifact_id: str
    cost_model: Optional[CostModel] = None

    def apply(self, state: State) -> Artifact:
        return Artifact(artifact_id=self.artifact_id, content=None)

    def cost(self, state: State) -> float:
        """Evaluation cost is higher and increases with depth (§14)."""
        if self.cost_model:
            return self.cost_model.compute(state)

        # Default: base cost higher for evaluation
        depth_penalty = len(state.trajectory) * 0.2
        return 5.0 * (1.0 + depth_penalty)

    def observability(self) -> dict[str, str]:
        return {"metrics": "objective_values", "correctness": "boolean"}
