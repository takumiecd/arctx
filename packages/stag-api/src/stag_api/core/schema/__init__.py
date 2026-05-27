"""Schema package — pure graph primitives and attached payloads."""

from stag_api.core.schema.graph import Node, Transition
from stag_api.core.schema.payloads import (
    CutPayload,
    NodePayload,
    Payload,
    PayloadBase,
    TransitionPayload,
    payload_from_dict,
    register_payload_class,
)
from stag_api.core.schema.requirements import Requirement
from stag_api.core.schema.snapshots import TraceContext

__all__ = [
    "CutPayload",
    "Node",
    "NodePayload",
    "Payload",
    "PayloadBase",
    "Requirement",
    "TraceContext",
    "Transition",
    "TransitionPayload",
    "payload_from_dict",
    "register_payload_class",
]
