"""Canonical state-transition records.

The new model uses points and arrows:

``StateNode -- TransitionRecord --> StateNode``.

``ActionSpec`` captures the plan made before execution. ``ActionResult``
captures the facts produced by execution. ``TransitionRecord`` stores those
source-of-truth records plus optional derived interpretations.
``StateContext`` is the view used by an agent when it needs to read past
evidence and predicted futures around the current state.
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

DecisionStatus = Literal[
    "accepted",
    "rejected",
    "needs_narrower_scope",
    "needs_more_evidence",
    "unsafe",
]

NodeStatus = Literal["predicted", "observed", "pruned", "merged"]
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
    """Reference to an artifact known by a state."""

    artifact_id: str
    artifact_type: str
    path: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class FindingRef:
    """Reference to reusable knowledge known by a state."""

    finding_id: str
    summary: str
    scope: str = ""
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionRef:
    """Compact prediction kept in a state snapshot."""

    prediction_id: str
    summary: str
    confidence: float | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class Budget:
    """Remaining resources available from a state."""

    max_transitions: int | None = None
    remaining_transitions: int | None = None
    max_wall_seconds: float | None = None
    remaining_wall_seconds: float | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class StateSnapshot:
    """The information available at a state.

    This is the state content. It does not store how to traverse the tree.
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
    EvidenceTree, PredictionTree, and StateContext.
    """

    state_id: str
    snapshot: StateSnapshot
    assumptions: tuple[str, ...] = ()
    confidence: float | None = None
    status: NodeStatus = "predicted"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class StateContext:
    """View of a current state inside past evidence and predicted futures."""

    current_state_id: str
    evidence_tree_id: str | None = None
    prediction_tree_id: str | None = None
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
class ActionSpec:
    """Execution plan chosen from a state before any side effect happens."""

    action_id: str
    action_type: ActionType
    intent: str
    inputs: dict[str, JSONValue] = field(default_factory=dict)
    expected_observation: dict[str, JSONValue] = field(default_factory=dict)
    expected_state_delta: dict[str, JSONValue] = field(default_factory=dict)
    estimated_cost: dict[str, JSONValue] = field(default_factory=dict)
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ActionResult:
    """Artifacts and raw outputs produced by executing an ActionSpec."""

    action_id: str
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
class TransitionRecord:
    """The source-of-truth arrow from one StateNode to another."""

    transition_id: str
    from_state_id: str
    to_state_id: str
    action_spec: ActionSpec
    action_result: ActionResult
    derived_records: tuple[DerivedRecord, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
