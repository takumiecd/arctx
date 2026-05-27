"""stag: records the process of optimization and problem-solving."""

from stag.core.graph_view import GraphView
from stag.core.run import RunHandle
from stag.core.run import init as _core_init
from stag.core.run_graph import RunGraph
from stag.core.schema import (
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
from stag.core.types import (
    TargetKind,
)
from stag.ext import attach_standard_extensions

__version__ = "0.1.0"


def init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle:
    """Create a run handle with the standard extension namespaces attached."""
    handle = _core_init(requirement, run_id=run_id)
    return attach_standard_extensions(handle)

__all__ = [
    "CutPayload",
    "GraphView",
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
