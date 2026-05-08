"""Schema package — pure DAG primitives and attached payloads."""

from optagent.core.schema.derived import (
    Decision,
    Evidence,
    Finding,
    Observation,
    PredictionError,
)
from optagent.core.schema.graph import Node, Transition
from optagent.core.schema.payloads import (
    CutPayload,
    DerivedPayload,
    MatchPayload,
    Payload,
    PayloadBase,
    ResultPayload,
    SnapshotPayload,
    payload_from_dict,
)
from optagent.core.schema.plans import Plan
from optagent.core.schema.requirements import Requirement
from optagent.core.schema.selections import (
    PredictionPath,
    PredictionSelection,
    PredictionStepRef,
)
from optagent.core.schema.snapshots import (
    ArtifactRef,
    Budget,
    FindingRef,
    PredictionRef,
    StateContext,
    StateDelta,
    StateSnapshot,
    TraceContext,
)

__all__ = [
    "ArtifactRef",
    "Budget",
    "CutPayload",
    "Decision",
    "DerivedPayload",
    "Evidence",
    "Finding",
    "FindingRef",
    "MatchPayload",
    "Node",
    "Observation",
    "Payload",
    "PayloadBase",
    "Plan",
    "PredictionError",
    "PredictionPath",
    "PredictionRef",
    "PredictionSelection",
    "PredictionStepRef",
    "Requirement",
    "ResultPayload",
    "SnapshotPayload",
    "StateContext",
    "StateDelta",
    "StateSnapshot",
    "TraceContext",
    "Transition",
    "payload_from_dict",
]
