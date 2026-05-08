"""Payload records attached to nodes or transitions.

A target (node or transition) may have multiple payloads attached.
Payloads are immutable and append-only; CutPayload in particular
encodes rewinds without ever deleting graph records.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Union

from optagent.core.schema.snapshots import StateSnapshot
from optagent.core.types import (
    DerivedType,
    JSONValue,
    MatchStatus,
    NodeStatus,
    PayloadType,
    ResultStatus,
    TargetKind,
    to_jsonable,
)


class PayloadBase(ABC):
    """Common contract for payload records attached to graph targets."""

    payload_id: str
    target_id: str
    target_kind: TargetKind
    payload_type: PayloadType

    @abstractmethod
    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-serializable representation."""


@dataclass(frozen=True)
class SnapshotPayload(PayloadBase):
    """Working memory snapshot attached to a node."""

    payload_id: str
    target_id: str
    snapshot: StateSnapshot
    snapshot_hash: str | None = None
    assumptions: tuple[str, ...] = ()
    confidence: float | None = None
    status: NodeStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="node", init=False)
    payload_type: PayloadType = field(default="snapshot", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ResultPayload(PayloadBase):
    """Action result attached to a transition.

    Same shape for predicted (forecasted) and observed (actual) results.
    The Dag containing the transition determines interpretation.
    """

    payload_id: str
    target_id: str
    status: ResultStatus
    artifacts: tuple[str, ...] = ()
    raw_outputs: tuple[str, ...] = ()
    logs: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    actual_cost: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="transition", init=False)
    payload_type: PayloadType = field(default="result", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class DerivedPayload(PayloadBase):
    """Interpretation derived from a transition's facts."""

    payload_id: str
    target_id: str
    derived_type: DerivedType
    payload: dict[str, JSONValue]
    generator: str
    confidence: float | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="transition", init=False)
    payload_type: PayloadType = field(default="derived", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class MatchPayload(PayloadBase):
    """Link from an observed transition to a predicted transition it realized."""

    payload_id: str
    target_id: str
    matched_transition_id: str
    match_status: MatchStatus
    prediction_error: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="transition", init=False)
    payload_type: PayloadType = field(default="match", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class CutPayload(PayloadBase):
    """Append-only cut marker on a transition.

    Anything reachable forward from the cut transition is treated as
    inactive at read time. The graph records themselves are not deleted.
    """

    payload_id: str
    target_id: str
    cut_at: str
    rewound_to_node_id: str
    reason: str | None = None
    user_id: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="transition", init=False)
    payload_type: PayloadType = field(default="cut", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


Payload = Union[
    SnapshotPayload,
    ResultPayload,
    DerivedPayload,
    MatchPayload,
    CutPayload,
]


def payload_from_dict(data: dict[str, JSONValue]) -> Payload:
    """Reconstruct a Payload subclass from its JSON dict form."""
    payload_type = data.get("payload_type")
    if payload_type == "snapshot":
        return _snapshot_from_dict(data)
    if payload_type == "result":
        return _result_from_dict(data)
    if payload_type == "derived":
        return _derived_from_dict(data)
    if payload_type == "match":
        return _match_from_dict(data)
    if payload_type == "cut":
        return _cut_from_dict(data)
    raise ValueError(f"unknown payload_type: {payload_type!r}")


def _snapshot_from_dict(data: dict[str, JSONValue]) -> SnapshotPayload:
    from optagent.core.schema.snapshots import (
        ArtifactRef,
        Budget,
        FindingRef,
        PredictionRef,
        StateSnapshot,
    )
    from optagent.core.schema.requirements import Requirement

    snap_d = data["snapshot"]
    assert isinstance(snap_d, dict)
    req_d = snap_d["requirement"]
    assert isinstance(req_d, dict)
    requirement = Requirement(
        requirement_id=str(req_d["requirement_id"]),
        target_type=str(req_d["target_type"]),
        target_id=str(req_d["target_id"]),
        objective=dict(req_d.get("objective") or {}),
        constraints=dict(req_d.get("constraints") or {}),
        metadata=dict(req_d.get("metadata") or {}),
    )
    artifacts = tuple(
        ArtifactRef(
            artifact_id=str(a["artifact_id"]),
            artifact_type=str(a["artifact_type"]),
            path=a.get("path"),
            metadata=dict(a.get("metadata") or {}),
        )
        for a in (snap_d.get("artifacts") or [])
    )
    knowledge = tuple(
        FindingRef(
            finding_id=str(k["finding_id"]),
            summary=str(k.get("summary") or ""),
            scope=str(k.get("scope") or ""),
            metadata=dict(k.get("metadata") or {}),
        )
        for k in (snap_d.get("knowledge") or [])
    )
    predictions = tuple(
        PredictionRef(
            prediction_id=str(p["prediction_id"]),
            summary=str(p.get("summary") or ""),
            confidence=p.get("confidence"),
            metadata=dict(p.get("metadata") or {}),
        )
        for p in (snap_d.get("predictions") or [])
    )
    budget_d = snap_d.get("budget")
    budget = (
        Budget(
            max_transitions=budget_d.get("max_transitions"),
            remaining_transitions=budget_d.get("remaining_transitions"),
            max_wall_seconds=budget_d.get("max_wall_seconds"),
            remaining_wall_seconds=budget_d.get("remaining_wall_seconds"),
            metadata=dict(budget_d.get("metadata") or {}),
        )
        if isinstance(budget_d, dict)
        else None
    )
    snapshot = StateSnapshot(
        requirement=requirement,
        artifacts=artifacts,
        knowledge=knowledge,
        open_questions=tuple(str(q) for q in (snap_d.get("open_questions") or [])),
        active_branches=tuple(str(b) for b in (snap_d.get("active_branches") or [])),
        predictions=predictions,
        budget=budget,
        metadata=dict(snap_d.get("metadata") or {}),
    )
    return SnapshotPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        snapshot=snapshot,
        snapshot_hash=data.get("snapshot_hash"),
        assumptions=tuple(str(a) for a in (data.get("assumptions") or [])),
        confidence=data.get("confidence"),
        status=data.get("status", "active"),
        metadata=dict(data.get("metadata") or {}),
    )


def _result_from_dict(data: dict[str, JSONValue]) -> ResultPayload:
    return ResultPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        status=data["status"],  # type: ignore[arg-type]
        artifacts=tuple(str(a) for a in (data.get("artifacts") or [])),
        raw_outputs=tuple(str(r) for r in (data.get("raw_outputs") or [])),
        logs=tuple(str(l) for l in (data.get("logs") or [])),
        metrics={str(k): float(v) for k, v in (data.get("metrics") or {}).items()},
        errors=tuple(str(e) for e in (data.get("errors") or [])),
        actual_cost=dict(data.get("actual_cost") or {}),
        metadata=dict(data.get("metadata") or {}),
    )


def _derived_from_dict(data: dict[str, JSONValue]) -> DerivedPayload:
    return DerivedPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        derived_type=data["derived_type"],  # type: ignore[arg-type]
        payload=dict(data.get("payload") or {}),
        generator=str(data.get("generator") or ""),
        confidence=data.get("confidence"),
        metadata=dict(data.get("metadata") or {}),
    )


def _match_from_dict(data: dict[str, JSONValue]) -> MatchPayload:
    return MatchPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        matched_transition_id=str(data["matched_transition_id"]),
        match_status=data["match_status"],  # type: ignore[arg-type]
        prediction_error=dict(data.get("prediction_error") or {}),
        metadata=dict(data.get("metadata") or {}),
    )


def _cut_from_dict(data: dict[str, JSONValue]) -> CutPayload:
    return CutPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        cut_at=str(data["cut_at"]),
        rewound_to_node_id=str(data["rewound_to_node_id"]),
        reason=data.get("reason"),
        user_id=data.get("user_id"),
        metadata=dict(data.get("metadata") or {}),
    )
