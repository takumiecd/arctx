"""Snapshot records and view contexts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from optagent.core.schema.requirements import Requirement
from optagent.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    artifact_type: str
    path: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class FindingRef:
    finding_id: str
    summary: str
    scope: str = ""
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionRef:
    prediction_id: str
    summary: str
    confidence: float | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class Budget:
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

    def compute_hash(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TraceContext:
    """Materialized view of observed history around a node."""

    current_node_id: str
    past_node_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    plan_ids: tuple[str, ...] = ()
    result_payload_ids: tuple[str, ...] = ()
    matched_transition_ids: tuple[str, ...] = ()
    derived_payload_ids: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
