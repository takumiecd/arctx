"""Derived interpretation records."""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.types import DecisionStatus, DerivedType, JSONValue, to_jsonable


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
