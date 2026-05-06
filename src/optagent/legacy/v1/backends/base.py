"""Backend base class for optimization providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from optagent.legacy.v1.core.models import Artifact, Hypothesis
from optagent.legacy.v1.core.state import OptimizationState


@dataclass
class HypothesisResult:
    """Result from hypothesis generation."""
    hypothesis: Hypothesis
    metadata: dict[str, Any]


class Backend(ABC):
    """Abstract base for optimization backends.
    
    Backends generate hypotheses and artifacts given an optimization state.
    Implementations: OpenCodeBackend, ClaudeBackend, LocalBackend, etc.
    """

    @abstractmethod
    def propose_hypotheses(
        self,
        state: OptimizationState,
        analysis: dict[str, Any],
    ) -> list[Hypothesis]:
        """Propose optimization hypotheses based on current state."""
        ...

    @abstractmethod
    def generate_artifact(
        self,
        hypothesis: Hypothesis,
        state: OptimizationState,
    ) -> Artifact:
        """Generate a concrete artifact for a hypothesis."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available (CLI installed, API key set, etc.)."""
        ...
