"""stag_api: records the process of optimization and problem-solving."""

from stag_api.core.graph_view import GraphView
from stag_api.core.run import RunHandle
from stag_api.core.run import init as _core_init
from stag_api.core.run_graph import RunGraph
from stag_api.core.schema import (
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
from stag_api.core.types import (
    TargetKind,
)

__version__ = "0.2.0b2"


def init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle:
    """Create a core run handle without enabling extensions."""
    return _core_init(requirement, run_id=run_id)

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
