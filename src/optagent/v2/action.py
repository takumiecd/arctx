"""§3 Action Space — domain-specific action kinds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from optagent.v2.state import Action, Artifact, State


@dataclass
class ApplyHypothesis(Action):
    """Action: apply an optimization hypothesis to produce a candidate."""
    hypothesis_id: str
    hypothesis_content: str

    def apply(self, state: State) -> Artifact:
        return Artifact(artifact_id=self.hypothesis_id, content=self.hypothesis_content)

    def cost(self, state: State) -> float:
        return 1.0

    def observability(self) -> dict[str, str]:
        return {"artifact": "candidate_artifact"}


@dataclass
class RunEvaluation(Action):
    """Action: evaluate a candidate artifact."""
    artifact_id: str

    def apply(self, state: State) -> Artifact:
        return Artifact(artifact_id=self.artifact_id, content=None)

    def cost(self, state: State) -> float:
        return 5.0

    def observability(self) -> dict[str, str]:
        return {"metrics": "objective_values", "correctness": "boolean"}
