"""Base strategy for optimization targets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from optagent.legacy.v1.core.models import Requirement
from optagent.legacy.v1.core.state import OptimizationState


class Strategy(ABC):
    """Abstract base for optimization strategies.

    Strategies define how to:
    1. Analyze optimization targets
    2. Generate baseline comparisons
    3. Apply optimization changes
    """

    @abstractmethod
    def initialize(self, state: OptimizationState) -> None:
        """Initialize strategy-specific state."""
        ...

    @abstractmethod
    def analyze(self, requirement: Requirement | None) -> dict[str, Any]:
        """Analyze the optimization target and return context."""
        ...

    @abstractmethod
    def get_baseline(self, requirement: Requirement) -> dict[str, Any]:
        """Get baseline measurement for comparison."""
        ...

    @abstractmethod
    def apply_changes(self, state: OptimizationState) -> None:
        """Apply accepted optimizations to the system."""
        ...

    @abstractmethod
    def validate_requirement(self, requirement: Requirement) -> bool:
        """Check if this strategy can handle the requirement."""
        ...
