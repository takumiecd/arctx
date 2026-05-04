"""optagent - Generalized optimization agent framework."""

__version__ = "0.1.0"

from optagent.core.manager import ManagerAgent
from optagent.core.models import (
    Artifact,
    Decision,
    Evidence,
    Hypothesis,
    OptimizationConfig,
    Requirement,
)
from optagent.core.state import OptimizationState
from optagent.core.workflow import WorkflowStep

__all__ = [
    "ManagerAgent",
    "Artifact",
    "Decision",
    "Evidence",
    "Hypothesis",
    "OptimizationConfig",
    "OptimizationState",
    "Requirement",
    "WorkflowStep",
]
