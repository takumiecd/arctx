"""Prediction and observed transition records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from optagent.core.schema.derived import DerivedRecord
from optagent.core.schema.results import ActionResult
from optagent.core.types import JSONValue, MatchStatus, PlanKind, to_jsonable


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
    to_predicted_state_id: str
    confidence: float | None = None
    assumptions: tuple[str, ...] = ()
    predicted_observation: dict[str, JSONValue] = field(default_factory=dict)
    predicted_state_delta: dict[str, JSONValue] = field(default_factory=dict)
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
class TraceCut:
    """Append-only record that marks a TraceDAG branch as cut.

    A rewind operation appends one ``TraceCut`` to the TraceDAG. The
    cut transition itself, every observed state reachable forward from
    it, every transition rooted in those states, and every derived
    record on those transitions are considered inactive after the cut.

    The DAG records (states, transitions, plans, results, derived
    records) themselves are never modified or deleted; cut/active
    membership is derived at read time by replaying the cut log.
    Adding a ``TraceCut`` therefore preserves source-of-truth history
    while letting consumers filter to the live subset.
    """

    cut_id: str
    cut_at: str
    rewound_to_state_id: str
    cut_transition_id: str
    reason: str | None = None
    actor_id: str | None = None
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
