"""optagent.

The public package is intentionally small while the project is being rebuilt
around the state-transition model documented in ``docs/ja``.
"""

from optagent.core.schema import (
    ActionResult,
    ActionSpec,
    Decision,
    Evidence,
    Finding,
    Observation,
    PredictionError,
    Requirement,
    StateDelta,
    StateNode,
    TransitionRecord,
)

__version__ = "0.1.0"

__all__ = [
    "ActionResult",
    "ActionSpec",
    "Decision",
    "Evidence",
    "Finding",
    "Observation",
    "PredictionError",
    "Requirement",
    "StateDelta",
    "StateNode",
    "TransitionRecord",
]
