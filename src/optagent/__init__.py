"""optagent.

The public package is intentionally small while the project is being rebuilt
around the state-transition model documented in ``docs/ja``.
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
from optagent.core.run import RunHandle, init
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
    MatchStatus,
    PlanKind,
    PlanStatus,
    StateKind,
    TransitionKind,
)

__version__ = "0.1.0"

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
    "MatchStatus",
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
    "RunHandle",
    "StateContext",
    "StateDelta",
    "StateKind",
    "StateNode",
    "StateSnapshot",
    "TraceContext",
    "TransitionKind",
    "init",
]
