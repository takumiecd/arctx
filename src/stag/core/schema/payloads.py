"""Payload records attached to nodes or transitions.

A target may have multiple payloads attached.
Payloads are immutable and append-only; CutPayload encodes cuts
without ever deleting graph records.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Union

from stag.core.types import (
    ActionType,
    JSONValue,
    PayloadType,
    ResultStatus,
    TargetKind,
    to_jsonable,
)


def _validate_probability(value: float | None, name: str) -> None:
    if value is not None and not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1] or None, got {value}")


def _opt_float(value: object) -> float | None:
    return float(value) if value is not None else None


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
class NotePayload(PayloadBase):
    """Lightweight memo attached to a node."""

    payload_id: str
    target_id: str
    text: str
    author: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="node", init=False)
    payload_type: PayloadType = field(default="note", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PlanPayload(PayloadBase):
    """Operation intent attached to an InputTransition."""

    payload_id: str
    target_id: str
    intent: str
    action_type: ActionType = "analysis"
    inputs: dict[str, JSONValue] = field(default_factory=dict)
    constraints: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="input_transition", init=False)
    payload_type: PayloadType = field(default="plan_payload", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionPayload(PayloadBase):
    """Predicted outcome attached to an OutputTransition."""

    payload_id: str
    target_id: str
    predicted_artifacts: tuple[str, ...] = ()
    predicted_metrics: dict[str, float] = field(default_factory=dict)
    rationale: str | None = None
    probability: float | None = None
    confidence: float | None = None
    predictor: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="output_transition", init=False)
    payload_type: PayloadType = field(default="prediction", init=False)

    def __post_init__(self) -> None:
        _validate_probability(self.probability, "probability")
        _validate_probability(self.confidence, "confidence")

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ResultPayload(PayloadBase):
    """Actual execution result attached to an OutputTransition."""

    payload_id: str
    target_id: str
    status: ResultStatus
    artifacts: tuple[str, ...] = ()
    raw_outputs: tuple[str, ...] = ()
    logs: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    actual_cost: dict[str, JSONValue] = field(default_factory=dict)
    matched_prediction_output_id: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="output_transition", init=False)
    payload_type: PayloadType = field(default="result", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class CommitEntry:
    """A single commit entry in a GitChangePayload commit_log."""

    sha: str
    subject: str
    author: str
    date: str  # ISO 8601 with timezone

    def to_dict(self) -> dict[str, str]:
        return {"sha": self.sha, "subject": self.subject, "author": self.author, "date": self.date}


@dataclass(frozen=True)
class DiffSummary:
    """Aggregate diff stats from git --shortstat."""

    files_changed: int
    insertions: int
    deletions: int

    def to_dict(self) -> dict[str, int]:
        return {
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions,
        }


@dataclass(frozen=True)
class GitChangePayload(PayloadBase):
    """Git repository change information attached to an OutputTransition.

    Captures the diff between base_commit..HEAD at the time stag git finish
    was executed. Co-exists with ResultPayload on the same OutputTransition.
    """

    payload_id: str
    target_id: str
    repo_root: str
    base_commit: str
    head_commit: str
    branch: str
    commits: tuple[str, ...] = ()
    commit_log: tuple[CommitEntry, ...] = ()
    diff_summary: DiffSummary = field(
        default_factory=lambda: DiffSummary(files_changed=0, insertions=0, deletions=0)
    )
    changed_files: tuple[str, ...] = ()
    patch_artifact: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: TargetKind = field(default="output_transition", init=False)
    payload_type: PayloadType = field(default="git_change", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "repo_root": self.repo_root,
            "base_commit": self.base_commit,
            "head_commit": self.head_commit,
            "branch": self.branch,
            "commits": list(self.commits),
            "commit_log": [c.to_dict() for c in self.commit_log],
            "diff_summary": self.diff_summary.to_dict(),
            "changed_files": list(self.changed_files),
            "patch_artifact": self.patch_artifact,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CutPayload(PayloadBase):
    """Append-only cut marker on an InputTransition or OutputTransition.

    - On an InputTransition: the entire plan and all its outputs become inactive.
    - On an OutputTransition: only that output becomes inactive.
    Inactivity is computed at read time; graph records are never deleted.
    """

    payload_id: str
    target_id: str
    target_kind: TargetKind
    cut_at: str
    reason: str | None = None
    user_id: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    payload_type: PayloadType = field(default="cut", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


Payload = Union[
    NotePayload,
    PlanPayload,
    PredictionPayload,
    ResultPayload,
    CutPayload,
    GitChangePayload,
]


def payload_from_dict(data: dict[str, JSONValue]) -> Payload:
    """Reconstruct a Payload subclass from its JSON dict form."""
    payload_type = data.get("payload_type")
    if payload_type == "note":
        return _note_from_dict(data)
    if payload_type == "plan_payload":
        return _plan_payload_from_dict(data)
    if payload_type == "prediction":
        return _prediction_from_dict(data)
    if payload_type == "result":
        return _result_from_dict(data)
    if payload_type == "cut":
        return _cut_from_dict(data)
    if payload_type == "git_change":
        return _git_change_from_dict(data)
    raise ValueError(f"unknown payload_type: {payload_type!r}")


def _note_from_dict(data: dict[str, JSONValue]) -> NotePayload:
    return NotePayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        text=str(data["text"]),
        author=data.get("author"),
        tags=tuple(str(t) for t in (data.get("tags") or [])),
        metadata=dict(data.get("metadata") or {}),
    )


def _plan_payload_from_dict(data: dict[str, JSONValue]) -> PlanPayload:
    return PlanPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        intent=str(data["intent"]),
        action_type=data.get("action_type", "analysis"),  # type: ignore[arg-type]
        inputs=dict(data.get("inputs") or {}),
        constraints=dict(data.get("constraints") or {}),
        assumptions=tuple(str(a) for a in (data.get("assumptions") or [])),
        safety_policy=dict(data.get("safety_policy") or {}),
        metadata=dict(data.get("metadata") or {}),
    )


def _prediction_from_dict(data: dict[str, JSONValue]) -> PredictionPayload:
    return PredictionPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        predicted_artifacts=tuple(str(a) for a in (data.get("predicted_artifacts") or [])),
        predicted_metrics={str(k): float(v) for k, v in (data.get("predicted_metrics") or {}).items()},
        rationale=data.get("rationale"),
        probability=_opt_float(data.get("probability")),
        confidence=_opt_float(data.get("confidence")),
        predictor=data.get("predictor"),
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
        matched_prediction_output_id=data.get("matched_prediction_output_id"),
        metadata=dict(data.get("metadata") or {}),
    )


def _cut_from_dict(data: dict[str, JSONValue]) -> CutPayload:
    return CutPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        target_kind=data["target_kind"],  # type: ignore[arg-type]
        cut_at=str(data["cut_at"]),
        reason=data.get("reason"),
        user_id=data.get("user_id"),
        metadata=dict(data.get("metadata") or {}),
    )


def _git_change_from_dict(data: dict[str, JSONValue]) -> GitChangePayload:
    raw_log = data.get("commit_log") or []
    commit_log = tuple(
        CommitEntry(
            sha=str(e["sha"]),
            subject=str(e["subject"]),
            author=str(e["author"]),
            date=str(e["date"]),
        )
        for e in raw_log
    )
    raw_summary = data.get("diff_summary") or {}
    diff_summary = DiffSummary(
        files_changed=int(raw_summary.get("files_changed", 0)),
        insertions=int(raw_summary.get("insertions", 0)),
        deletions=int(raw_summary.get("deletions", 0)),
    )
    return GitChangePayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        repo_root=str(data["repo_root"]),
        base_commit=str(data["base_commit"]),
        head_commit=str(data["head_commit"]),
        branch=str(data["branch"]),
        commits=tuple(str(c) for c in (data.get("commits") or [c.sha for c in commit_log])),
        commit_log=commit_log,
        diff_summary=diff_summary,
        changed_files=tuple(str(f) for f in (data.get("changed_files") or [])),
        patch_artifact=data.get("patch_artifact"),
        metadata=dict(data.get("metadata") or {}),
    )
