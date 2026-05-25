"""Schema package — pure graph primitives and attached payloads."""

from stag.core.schema.graph import Node, Transition
from stag.core.schema.payloads import (
    CommitEntry,
    CutPayload,
    DiffSummary,
    GitChangePayload,
    NodePayload,
    Payload,
    PayloadBase,
    TransitionPayload,
    payload_from_dict,
    register_payload_class,
)
from stag.core.schema.requirements import Requirement
from stag.core.schema.snapshots import TraceContext

__all__ = [
    "CommitEntry",
    "CutPayload",
    "DiffSummary",
    "GitChangePayload",
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
