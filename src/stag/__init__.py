"""stag: records the process of optimization and problem-solving."""

from stag.core.graph_view import GraphView
from stag.core.run import RunHandle, init
from stag.core.run_graph import RunGraph
from stag.core.schema import (
    CommitEntry,
    CutPayload,
    DiffSummary,
    GitChangePayload,
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

__version__ = "0.1.0"

__all__ = [
    "CommitEntry",
    "CutPayload",
    "DiffSummary",
    "GitChangePayload",
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
