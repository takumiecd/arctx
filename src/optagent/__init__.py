"""optagent.

The public package is intentionally small while the project is being rebuilt
around the state-transition model documented in ``docs/ja``.
"""

from optagent.core.schema import (
    ActionResult,
    ActionSpec,
    ArtifactRef,
    Budget,
    Decision,
    DerivedRecord,
    DerivedType,
    Evidence,
    Finding,
    FindingRef,
    Observation,
    PredictionError,
    PredictionRef,
    Requirement,
    StateContext,
    StateDelta,
    StateNode,
    StateSnapshot,
    TransitionRecord,
)

__version__ = "0.1.0"

__all__ = [
    "ActionResult",
    "ActionSpec",
    "ArtifactRef",
    "Budget",
    "Decision",
    "DerivedRecord",
    "DerivedType",
    "Evidence",
    "Finding",
    "FindingRef",
    "Observation",
    "PredictionError",
    "PredictionRef",
    "Requirement",
    "StateContext",
    "StateDelta",
    "StateNode",
    "StateSnapshot",
    "TransitionRecord",
]
