"""Compatibility exports for core records.

The concrete records live in focused modules:

- ``types`` for shared literal types and JSON helpers
- ``requirements`` for run requirements
- ``state`` for state nodes and context views
- ``plans`` for PredictionPlan and ExecutionPlan
- ``results`` for ActionResult
- ``derived`` for derived interpretation records
- ``transitions`` for predicted and observed transitions

PredictionPlan and ExecutionPlan are intentionally not collapsed into a common
public ``Plan`` alias. They are different records with different valid contexts.
"""

from optagent.core.derived import (
    Decision,
    DerivedRecord,
    Evidence,
    Finding,
    Observation,
    PredictionError,
)
from optagent.core.plans import ExecutionPlan, PredictionPlan
from optagent.core.requirements import Requirement
from optagent.core.results import ActionResult
from optagent.core.state import (
    ArtifactRef,
    Budget,
    FindingRef,
    PredictionRef,
    StateContext,
    StateDelta,
    StateNode,
    StateSnapshot,
    TraceContext,
)
from optagent.core.transitions import (
    ObservedTransition,
    PredictedTransition,
    PredictionMatch,
    PredictionPath,
    PredictionSelection,
    PredictionStepRef,
)
from optagent.core.types import (
    ActionType,
    DecisionStatus,
    DerivedType,
    JSONValue,
    MatchStatus,
    NodeStatus,
    PlanKind,
    PlanStatus,
    ResultStatus,
    StateKind,
    TransitionKind,
    to_jsonable,
)

__all__ = [
    "ActionResult",
    "ActionType",
    "ArtifactRef",
    "Budget",
    "Decision",
    "DecisionStatus",
    "DerivedRecord",
    "DerivedType",
    "Evidence",
    "ExecutionPlan",
    "Finding",
    "FindingRef",
    "JSONValue",
    "MatchStatus",
    "NodeStatus",
    "Observation",
    "ObservedTransition",
    "PlanKind",
    "PlanStatus",
    "PredictionError",
    "PredictionMatch",
    "PredictionPath",
    "PredictionPlan",
    "PredictionRef",
    "PredictionSelection",
    "PredictionStepRef",
    "PredictedTransition",
    "Requirement",
    "ResultStatus",
    "StateContext",
    "StateDelta",
    "StateKind",
    "StateNode",
    "StateSnapshot",
    "TraceContext",
    "TransitionKind",
    "to_jsonable",
]
