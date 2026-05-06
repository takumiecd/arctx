"""Canonical state-transition records.

The new model uses points and arrows:

``StateNode -- TransitionRecord --> StateNode``.

``ActionSpec`` captures the plan made before execution. ``ActionResult``
captures the facts produced by execution. ``TransitionRecord`` binds them to
evidence, decision, finding, and the state delta that creates the next node.
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
class StateNode:
    """A point in a prediction or evidence tree."""

    state_id: str
    depth: int
    requirement_id: str
    branch_id: str = "main"
    parent_state_ids: tuple[str, ...] = ()
    state_snapshot: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    confidence: float | None = None
    status: NodeStatus = "predicted"
    linked_transition_id: str | None = None

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
class TransitionRecord:
    """The arrow from one StateNode to another."""

    transition_id: str
    from_state_id: str
    to_state_id: str
    action_spec: ActionSpec
    action_result: ActionResult | None = None
    observation: Observation | None = None
    evidence: Evidence | None = None
    prediction_error: PredictionError | None = None
    decision: Decision | None = None
    finding: Finding | None = None
    state_delta: StateDelta = field(default_factory=StateDelta)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
