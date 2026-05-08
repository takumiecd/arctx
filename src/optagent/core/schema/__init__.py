"""Schema package — pure graph primitives and attached payloads."""

from optagent.core.schema.graph import InputTransition, Node, OutputTransition
from optagent.core.schema.payloads import (
    CutPayload,
    NotePayload,
    Payload,
    PayloadBase,
    PlanPayload,
    PredictionPayload,
    ResultPayload,
    payload_from_dict,
)
from optagent.core.schema.requirements import Requirement
from optagent.core.schema.snapshots import TraceContext

__all__ = [
    "CutPayload",
    "InputTransition",
    "NotePayload",
    "Node",
    "OutputTransition",
    "Payload",
    "PayloadBase",
    "PlanPayload",
    "PredictionPayload",
    "Requirement",
    "ResultPayload",
    "TraceContext",
    "payload_from_dict",
]
