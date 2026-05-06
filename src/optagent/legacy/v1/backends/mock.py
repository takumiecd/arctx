"""Mock backend for testing."""

from __future__ import annotations

from typing import Any

from optagent.legacy.v1.backends.base import Backend
from optagent.legacy.v1.core.models import Artifact, Hypothesis
from optagent.legacy.v1.core.state import OptimizationState


class MockBackend(Backend):
    """Backend that returns canned responses for testing."""

    def __init__(
        self,
        hypotheses: list[Hypothesis] | None = None,
        artifacts: dict[str, Artifact] | None = None,
    ) -> None:
        self._hypotheses = hypotheses or []
        self._artifacts = artifacts or {}

    def propose_hypotheses(
        self,
        state: OptimizationState,
        analysis: dict[str, Any],
    ) -> list[Hypothesis]:
        return list(self._hypotheses)

    def generate_artifact(
        self,
        hypothesis: Hypothesis,
        state: OptimizationState,
    ) -> Artifact:
        if hypothesis.id in self._artifacts:
            return self._artifacts[hypothesis.id]
        return Artifact(
            hypothesis_id=hypothesis.id,
            artifact_type="mock",
            content="# mock artifact",
        )

    def is_available(self) -> bool:
        return True
