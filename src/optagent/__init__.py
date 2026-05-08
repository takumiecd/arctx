"""optagent.

The public package is intentionally small while the project is being rebuilt
around the state-transition model documented in ``docs/ja``.
"""

from optagent.core.dag import Dag
from optagent.core.run import RunHandle, init
from optagent.core.schema import (
    ArtifactRef,
    Budget,
    CutPayload,
    DerivedPayload,
    FindingRef,
    MatchPayload,
    Node,
    Payload,
    PayloadBase,
    Plan,
    PredictionPath,
    PredictionRef,
    PredictionSelection,
    PredictionStepRef,
    Requirement,
    ResultPayload,
    SnapshotPayload,
    StateSnapshot,
    TraceContext,
    Transition,
)
from optagent.core.types import (
    ActionType,
    DagRole,
    DerivedType,
    MatchStatus,
    PayloadType,
    PlanStatus,
    TargetKind,
)

__version__ = "0.1.0"

__all__ = [
    "ActionType",
    "ArtifactRef",
    "Budget",
    "CutPayload",
    "Dag",
    "DagRole",
    "DerivedPayload",
    "DerivedType",
    "FindingRef",
    "MatchPayload",
    "MatchStatus",
    "Node",
    "Payload",
    "PayloadBase",
    "PayloadType",
    "Plan",
    "PlanStatus",
    "PredictionPath",
    "PredictionRef",
    "PredictionSelection",
    "PredictionStepRef",
    "Requirement",
    "ResultPayload",
    "RunHandle",
    "SnapshotPayload",
    "StateSnapshot",
    "TargetKind",
    "TraceContext",
    "Transition",
    "init",
]
