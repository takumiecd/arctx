"""arctx: records the process of optimization and problem-solving."""

from __future__ import annotations

from arctx.core.run import RunHandle
from arctx.core.run import init as _core_init
from arctx.core.run_graph import RunGraph
from arctx.core.schema import (
    CutPayload,
    Node,
    NodePayload,
    Payload,
    PayloadBase,
    Requirement,
    TraceContext,
    Transition,
    TransitionPayload,
    register_payload_class,
)
from arctx.core.types import (
    TargetKind,
)

__version__ = "0.3.0b1"


def init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle:
    """Create a core run handle without enabling extensions."""
    return _core_init(requirement, run_id=run_id)

__all__ = [
    "CutPayload",
    "Node",
    "NodePayload",
    "Payload",
    "PayloadBase",
    "Requirement",
    "RunGraph",
    "RunHandle",
    "TargetKind",
    "TraceContext",
    "Transition",
    "TransitionPayload",
    "init",
    "register_payload_class",
]
