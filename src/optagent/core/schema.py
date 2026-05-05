"""Canonical schema for auditable optimization attempts.

These records form the Evidence Graph used across workflows:

Requirement -> Attempt -> Hypothesis -> Action -> Artifact -> Observation
-> Evidence -> Decision -> Finding

The schema is intentionally conservative and JSON-friendly. Domain-specific
details belong in ``metadata`` until they deserve a typed field.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Literal, cast


DecisionStatus = Literal[
    "accepted",
    "rejected",
    "needs_narrower_scope",
    "needs_more_evidence",
    "unsafe",
]


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def canonical_decision_status(value: str) -> DecisionStatus:
    """Map workflow-specific decision labels into the canonical status set."""
    if value == "inconclusive":
        return "needs_more_evidence"
    if value in {"accepted", "rejected", "needs_narrower_scope", "needs_more_evidence", "unsafe"}:
        return cast(DecisionStatus, value)
    return "needs_more_evidence"


@dataclass(frozen=True)
class RequirementRecord:
    """Fixed optimization target and objective."""

    requirement_id: str
    target_type: str
    target_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    objective: dict[str, Any] = field(default_factory=dict)
    promotion: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)

    @classmethod
    def from_requirement(
        cls,
        requirement: Any,
        requirement_id: str | None = None,
    ) -> "RequirementRecord":
        """Build a canonical requirement from workflow or domain requirement objects."""
        target_type = getattr(requirement, "target_type", "unknown")
        target_id = getattr(requirement, "target_id", str(requirement))
        return cls(
            requirement_id=requirement_id or f"{target_type}:{target_id}",
            target_type=target_type,
            target_id=target_id,
            parameters=dict(getattr(requirement, "parameters", {}) or {}),
            constraints=dict(getattr(requirement, "constraints", {}) or {}),
            objective=dict(getattr(requirement, "objective", {}) or {}),
            promotion=dict(getattr(requirement, "promotion", {}) or {}),
        )


@dataclass
class HypothesisRecord:
    """Falsifiable optimization hypothesis."""

    hypothesis_id: str
    claim: str = ""
    proposed_change: str = ""
    expected_effect: str = ""
    risk: str = ""
    target_keys: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)

    @classmethod
    def from_hypothesis(cls, hypothesis: Any) -> "HypothesisRecord":
        description = getattr(hypothesis, "description", "")
        return cls(
            hypothesis_id=getattr(hypothesis, "id", ""),
            claim=getattr(hypothesis, "claim", description),
            proposed_change=getattr(hypothesis, "proposed_change", ""),
            expected_effect=getattr(hypothesis, "expected_effect", ""),
            risk=getattr(hypothesis, "risk", ""),
            target_keys=list(getattr(hypothesis, "target_keys", []) or []),
            metadata=dict(getattr(hypothesis, "metadata", {}) or {}),
        )


@dataclass
class ActionRecord:
    """Action as the search, cost, replay, and audit unit."""

    action_id: str
    action_type: str
    estimated_cost: float | None = None
    expected_observation_schema: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass
class ArtifactRecord:
    """Candidate artifact produced by an action."""

    artifact_id: str
    artifact_type: str
    path: str | None = None
    parent_artifact_id: str | None = None
    registry_policy: str = "declare_only"
    changed_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)

    @classmethod
    def from_artifact(cls, artifact: Any) -> "ArtifactRecord":
        artifact_id = getattr(artifact, "artifact_id", None) or getattr(
            artifact, "artifact_type", "artifact"
        )
        return cls(
            artifact_id=str(artifact_id),
            artifact_type=getattr(artifact, "artifact_type", "unknown"),
            path=getattr(artifact, "patch_path", None),
            registry_policy=getattr(artifact, "registry_policy", "declare_only"),
            changed_files=list(getattr(artifact, "changed_files", []) or []),
            metadata=dict(getattr(artifact, "metadata", {}) or {}),
        )


@dataclass
class ObservationRecord:
    """Raw observation from executing an action."""

    observation_id: str
    action_id: str
    raw_output_path: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass
class EvidenceRecord:
    """Normalized evidence derived from observations."""

    evidence_id: str
    artifact_id: str
    correctness: str = "unknown"
    eligible: bool = False
    speedup: float | None = None
    baseline: str = ""
    eligible_scope: str = ""
    regressions: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    raw_output_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)

    @classmethod
    def from_evidence(cls, evidence: Any) -> "EvidenceRecord":
        metrics: dict[str, float] = {}
        if getattr(evidence, "mean_ms_candidate", None) is not None:
            metrics["mean_ms_candidate"] = getattr(evidence, "mean_ms_candidate")
        if getattr(evidence, "mean_ms_baseline", None) is not None:
            metrics["mean_ms_baseline"] = getattr(evidence, "mean_ms_baseline")
        return cls(
            evidence_id=f"evidence:{getattr(evidence, 'hypothesis_id', '')}",
            artifact_id=str(getattr(evidence, "artifact_id", "")),
            correctness=getattr(evidence, "correctness", "unknown"),
            eligible=bool(getattr(evidence, "eligible", False)),
            speedup=getattr(evidence, "speedup", None),
            baseline=getattr(evidence, "baseline_spec", ""),
            regressions=list(getattr(evidence, "regressions", []) or []),
            metrics=metrics,
            raw_output_path=getattr(evidence, "raw_output", ""),
            metadata=dict(getattr(evidence, "metadata", {}) or {}),
        )


@dataclass
class DecisionRecord:
    """Promotion decision for an attempt."""

    decision_id: str
    status: DecisionStatus
    reason: str = ""
    policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass
class FindingRecord:
    """Reusable knowledge extracted from an attempt."""

    finding_id: str
    summary: str
    avoid: str = ""
    promising: str = ""
    scope: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass
class AttemptRecord:
    """One node in the Evidence Graph."""

    attempt_id: str
    requirement_id: str
    parent_attempt_id: str | None = None
    hypothesis: HypothesisRecord | None = None
    action: ActionRecord | None = None
    artifact: ArtifactRecord | None = None
    observation: ObservationRecord | None = None
    evidence: EvidenceRecord | None = None
    decision: DecisionRecord | None = None
    finding: FindingRecord | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)
