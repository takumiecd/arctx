"""State records and state-context views."""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.schema.requirements import Requirement
from optagent.core.types import JSONValue, NodeStatus, StateKind, to_jsonable


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
    """Working memory used to choose the next plan."""

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
    """A state point."""

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
