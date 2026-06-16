"""Schema package — pure graph primitives and attached payloads."""

from arctx.core.schema.graph import Node, Step
from arctx.core.schema.payloads import (
    CutPayload,
    NodePayload,
    Payload,
    PayloadBase,
    StepPayload,
    payload_from_dict,
    register_payload_class,
)
from arctx.core.schema.requirements import Requirement
from arctx.core.schema.snapshots import TraceContext
from arctx.core.schema.work import Lane, WorkEvent, WorkSession

__all__ = [
    "CutPayload",
    "Lane",
    "Node",
    "NodePayload",
    "Payload",
    "PayloadBase",
    "Requirement",
    "TraceContext",
    "Step",
    "StepPayload",
    "WorkEvent",
    "WorkSession",
    "payload_from_dict",
    "register_payload_class",
]
