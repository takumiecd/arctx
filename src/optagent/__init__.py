"""optagent: records the process of optimization and problem-solving."""

from optagent.core.graph_view import GraphView
from optagent.core.run import RunHandle, init
from optagent.core.run_graph import RunGraph
from optagent.core.schema import (
    CutPayload,
    InputTransition,
    NotePayload,
    Node,
    OutputTransition,
    Payload,
    PayloadBase,
    PlanPayload,
    PredictionPayload,
    Requirement,
    ResultPayload,
    TraceContext,
)
from optagent.core.types import (
    ActionType,
    PayloadType,
    ResultStatus,
    TargetKind,
)

__version__ = "0.1.0"

__all__ = [
    "ActionType",
    "CutPayload",
    "GraphView",
    "InputTransition",
    "NotePayload",
    "Node",
    "OutputTransition",
    "Payload",
    "PayloadBase",
    "PayloadType",
    "PlanPayload",
    "PredictionPayload",
    "Requirement",
    "ResultPayload",
    "ResultStatus",
    "RunGraph",
    "RunHandle",
    "TargetKind",
    "TraceContext",
    "init",
]
