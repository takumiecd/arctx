"""Workflow engine for optimization steps."""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Callable


class WorkflowStep(Enum):
    """Standard optimization workflow steps."""
    INITIALIZE = auto()
    ANALYZE_TARGET = auto()
    PROPOSE_HYPOTHESES = auto()
    GENERATE_ARTIFACTS = auto()
    EVALUATE_ARTIFACTS = auto()
    VALIDATE_RESULTS = auto()
    MAKE_DECISION = auto()
    APPLY_CHANGES = auto()
    FINALIZE = auto()


class Workflow:
    """Deterministic workflow engine.
    
    Provides hooks for each step so strategies can customize behavior.
    """

    def __init__(self) -> None:
        self._hooks: dict[WorkflowStep, list[Callable]] = {
            step: [] for step in WorkflowStep
        }

    def register_hook(self, step: WorkflowStep, callback: Callable) -> None:
        """Register a callback for a specific workflow step."""
        self._hooks[step].append(callback)

    def execute_step(self, step: WorkflowStep, context: dict[str, Any]) -> dict[str, Any]:
        """Execute all hooks for a step, passing context through."""
        for hook in self._hooks[step]:
            context = hook(context) or context
        return context

    def get_default_steps(self) -> list[WorkflowStep]:
        """Get the default workflow sequence."""
        return [
            WorkflowStep.INITIALIZE,
            WorkflowStep.ANALYZE_TARGET,
            WorkflowStep.PROPOSE_HYPOTHESES,
            WorkflowStep.GENERATE_ARTIFACTS,
            WorkflowStep.EVALUATE_ARTIFACTS,
            WorkflowStep.VALIDATE_RESULTS,
            WorkflowStep.MAKE_DECISION,
            WorkflowStep.FINALIZE,
        ]
