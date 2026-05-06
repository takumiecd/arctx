"""Base evaluator for optimization artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from optagent.legacy.v1.core.models import Artifact, Evidence
from optagent.legacy.v1.core.state import OptimizationState


class Evaluator(ABC):
    """Abstract base for artifact evaluators.
    
    Evaluators measure performance, correctness, or other metrics
    for generated artifacts.
    """

    @abstractmethod
    def evaluate(
        self,
        artifact: Artifact,
        state: OptimizationState,
    ) -> Evidence:
        """Evaluate an artifact and return evidence.
        
        Parameters
        ----------
        artifact:
            The artifact to evaluate.
        state:
            Current optimization state (includes requirement, baseline, etc.).
        
        Returns
        -------
        Evidence with evaluation results.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this evaluator can run in the current environment."""
        ...
