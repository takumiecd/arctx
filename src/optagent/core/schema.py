"""Canonical prediction and trace records.

The rebuilt model separates unexecuted futures from observed facts:

``PredictionDAG`` stores predicted states, plans, and predicted transitions.
``TraceDAG`` stores observed states, execution plans, and observed transitions.

Plans hold the executable intent directly. There is no separate ``ActionSpec``.
``ActionResult`` is only attached to an ``ObservedTransition`` after execution.
Derived records are structured notes made from source-of-truth facts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Literal, TypeAlias


JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]

ActionType = Literal[
    "investigation",
    "implementation",
    "verification",
    "analysis",
    "scope_refinement",
]

StateKind = Literal["observed", "predicted"]
PlanKind = Literal["execution", "prediction"]
TransitionKind = Literal["observed", "predicted"]
MatchStatus = Literal["exact", "compatible", "partial", "mismatch"]
DecisionStatus = Literal[
    "accepted",
    "rejected",
    "needs_narrower_scope",
    "needs_more_evidence",
    "unsafe",
]

PlanStatus = Literal["active", "promoted", "executed", "stale", "pruned", "cancelled"]
NodeStatus = Literal["active", "stale", "pruned", "merged"]
ResultStatus = Literal["completed", "failed", "timeout", "skipped"]
DerivedType = Literal[
    "observation",
    "evidence",
    "prediction_error",
    "decision",
    "finding",
    "state_delta",
    "summary",
]


def to_jsonable(value: Any) -> JSONValue:
    """Convert dataclass records and paths into JSON-friendly values."""
    if is_dataclass(value):
        return {str(k): to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


@dataclass(frozen=True)
class Requirement:
    """Fixed optimization target for a run."""

    requirement_id: str
    target_type: str
    target_id: str
    objective: dict[str, JSONValue] = field(default_factory=dict)
    constraints: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to a source-of-truth artifact known by a state."""

    artifact_id: str
    artifact_type: str
    path: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class FindingRef:
    """Reference to compressed derived knowledge known by a state."""

    finding_id: str
    summary: str
    scope: str = ""
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionRef:
    """Compact forecast cache kept in a state snapshot."""

    prediction_id: str
    summary: str
    confidence: float | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class Budget:
    """Execution/resource state available from a state."""

    max_transitions: int | None = None
    remaining_transitions: int | None = None
    max_wall_seconds: float | None = None
    remaining_wall_seconds: float | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class StateSnapshot:
    """Working memory used to choose the next action.

    A snapshot is not source of truth. It combines fixed inputs, references to
    facts, resource state, and compressed derived knowledge. It does not store
    how to traverse the tree.
    """

    requirement: Requirement
    artifacts: tuple[ArtifactRef, ...] = ()
    knowledge: tuple[FindingRef, ...] = ()
    open_questions: tuple[str, ...] = ()
    active_branches: tuple[str, ...] = ()
    predictions: tuple[PredictionRef, ...] = ()
    budget: Budget | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class StateNode:
    """A state point.

    The node stores state content only. Past and future traversal is handled by
    TraceDAG, PredictionDAG, and StateContext.
    """

    state_id: str
    state_kind: StateKind
    snapshot: StateSnapshot
    snapshot_hash: str | None = None
    anchor_observed_state_id: str | None = None
    assumptions: tuple[str, ...] = ()
    confidence: float | None = None
    status: NodeStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class StateContext:
    """View of a current state inside past evidence and predicted futures."""

    current_state_id: str
    trace_dag_id: str | None = None
    prediction_dag_id: str | None = None
    current_depth: int | None = None
    active_branch_ids: tuple[str, ...] = ()
    focus_transition_ids: tuple[str, ...] = ()
    past_depth: int | None = None
    future_depth: int | None = None
    include_pruned: bool = False
    include_unsafe: bool = True
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class TraceContext:
    """Materialized view of observed history around a state."""

    current_state_id: str
    past_state_ids: tuple[str, ...] = ()
    observed_transition_ids: tuple[str, ...] = ()
    execution_plan_ids: tuple[str, ...] = ()
    action_result_ids: tuple[str, ...] = ()
    matched_predicted_transition_ids: tuple[str, ...] = ()
    derived_record_ids: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionPlan:
    """Hypothetical plan that only exists inside a PredictionDAG."""

    plan_id: str
    plan_kind: Literal["prediction"]
    from_predicted_state_id: str
    action_type: ActionType
    intent: str
    inputs: dict[str, JSONValue] = field(default_factory=dict)
    expected_observation: dict[str, JSONValue] = field(default_factory=dict)
    expected_state_delta: dict[str, JSONValue] = field(default_factory=dict)
    estimated_cost: dict[str, JSONValue] = field(default_factory=dict)
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    confidence: float | None = None
    status: PlanStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ExecutionPlan:
    """Plan grounded in an observed state and safe to pass to an executor."""

    plan_id: str
    plan_kind: Literal["execution"]
    from_observed_state_id: str
    action_type: ActionType
    intent: str
    inputs: dict[str, JSONValue] = field(default_factory=dict)
    expected_observation: dict[str, JSONValue] = field(default_factory=dict)
    expected_state_delta: dict[str, JSONValue] = field(default_factory=dict)
    estimated_cost: dict[str, JSONValue] = field(default_factory=dict)
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    status: PlanStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


Plan = PredictionPlan | ExecutionPlan


@dataclass(frozen=True)
class ActionResult:
    """Artifacts and raw outputs produced by executing an ExecutionPlan."""

    result_id: str
    execution_plan_id: str
    status: ResultStatus
    artifacts: tuple[str, ...] = ()
    raw_outputs: tuple[str, ...] = ()
    logs: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    actual_cost: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class Observation:
    """Raw observation derived from an action result."""

    observation_id: str
    summary: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    raw_output_refs: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class Evidence:
    """Normalized evidence used for promotion and learning."""

    evidence_id: str
    correctness: str = "unknown"
    eligible_scope: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    regressions: tuple[str, ...] = ()
    raw_observation_ids: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionError:
    """Difference between expected and observed results."""

    prediction_error_id: str
    matched: tuple[str, ...] = ()
    missed: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    severity: str = "unknown"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionMatch:
    """How an observed transition matches a previously predicted outcome."""

    matched_predicted_transition_id: str
    match_status: MatchStatus
    prediction_error: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class Decision:
    """Promotion decision made from evidence and policy."""

    decision_id: str
    status: DecisionStatus
    reason: str = ""
    policy: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class Finding:
    """Reusable knowledge learned from a transition."""

    finding_id: str
    summary: str
    promising: str = ""
    avoid: str = ""
    scope: str = ""
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class StateDelta:
    """Changes applied to a StateNode to produce the next StateNode."""

    artifact_changes: dict[str, JSONValue] = field(default_factory=dict)
    knowledge_changes: dict[str, JSONValue] = field(default_factory=dict)
    open_question_changes: dict[str, JSONValue] = field(default_factory=dict)
    branch_changes: dict[str, JSONValue] = field(default_factory=dict)
    prediction_changes: dict[str, JSONValue] = field(default_factory=dict)
    budget_changes: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class DerivedRecord:
    """Interpretation or compression derived from transition facts."""

    derived_id: str
    source_transition_id: str
    derived_type: DerivedType
    payload: dict[str, JSONValue]
    generator: str
    confidence: float | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictedTransition:
    """Predicted outcome of running a plan."""

    transition_id: str
    transition_kind: Literal["predicted"]
    parent_plan_id: str
    parent_plan_kind: PlanKind
    from_state_id: str
    outcome_id: str
    outcome_label: str
    predicted_result: dict[str, JSONValue]
    predicted_state_delta: dict[str, JSONValue]
    to_predicted_state_id: str
    confidence: float | None = None
    assumptions: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ObservedTransition:
    """Observed source-of-truth transition in the TraceDAG."""

    transition_id: str
    transition_kind: Literal["observed"]
    execution_plan_id: str
    from_observed_state_id: str
    to_observed_state_id: str
    action_result: ActionResult
    matched_predicted_transition_id: str | None = None
    prediction_match: PredictionMatch | None = None
    derived_records: tuple[DerivedRecord, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionStepRef:
    """Selected prediction step inside a PredictionPath."""

    prediction_plan_id: str
    selected_predicted_transition_id: str
    from_predicted_state_id: str
    to_predicted_state_id: str

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionPath:
    """Selected path through the PredictionDAG."""

    path_id: str
    anchor_observed_state_id: str
    steps: tuple[PredictionStepRef, ...]
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionSelection:
    """Selection of predicted transitions to promote or compare."""

    selection_id: str
    selected_transition_ids: tuple[str, ...]
    selected_path_id: str | None = None
    reason: str = ""
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
