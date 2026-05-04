"""Data models for optimization workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Requirement:
    """Target specification for optimization.
    
    This is intentionally generic - the strategy interprets the fields.
    """
    target_type: str  # e.g., "kernel", "config", "query"
    target_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    objective: dict[str, Any] = field(default_factory=lambda: {
        "metric": "latency_ms",
        "direction": "minimize",
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "parameters": dict(self.parameters),
            "constraints": dict(self.constraints),
            "objective": dict(self.objective),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Requirement:
        return cls(
            target_type=data["target_type"],
            target_id=data["target_id"],
            parameters=dict(data.get("parameters", {})),
            constraints=dict(data.get("constraints", {})),
            objective=dict(data.get("objective", {"metric": "latency_ms", "direction": "minimize"})),
        )


@dataclass
class Hypothesis:
    """An optimization hypothesis proposed by a backend."""
    id: str
    description: str
    strategy_type: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "strategy_type": self.strategy_type,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }


@dataclass
class Artifact:
    """A concrete optimization artifact (code, config, etc.)."""
    hypothesis_id: str
    artifact_type: str  # e.g., "code", "config", "patch"
    content: str = ""
    files: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "artifact_type": self.artifact_type,
            "content": self.content,
            "files": list(self.files),
            "metadata": dict(self.metadata),
        }


@dataclass
class Evidence:
    """Evaluation evidence for an artifact."""
    hypothesis_id: str
    artifact_id: str
    metric_value: float | None = None
    baseline_value: float | None = None
    speedup: float | None = None
    is_correct: bool = False
    is_eligible: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    raw_data: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "artifact_id": self.artifact_id,
            "metric_value": self.metric_value,
            "baseline_value": self.baseline_value,
            "speedup": self.speedup,
            "is_correct": self.is_correct,
            "is_eligible": self.is_eligible,
            "details": dict(self.details),
            "raw_data": self.raw_data,
        }


@dataclass
class Decision:
    """Final optimization decision."""
    round_index: int
    accepted: bool
    reason: str
    promoted: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "accepted": self.accepted,
            "reason": self.reason,
            "promoted": list(self.promoted),
            "rejected": list(self.rejected),
        }


@dataclass
class OptimizationConfig:
    """Global optimization configuration."""
    max_rounds: int = 3
    target_speedup: float = 1.05
    require_correctness: bool = True
    allow_promotion: bool = False
    backup_dir: str = "./optagent_backups"

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_rounds": self.max_rounds,
            "target_speedup": self.target_speedup,
            "require_correctness": self.require_correctness,
            "allow_promotion": self.allow_promotion,
            "backup_dir": self.backup_dir,
        }
