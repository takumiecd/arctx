"""State model for optimization agent.

Based on kernel_optimizer_architecture.md:
Algorithm state: X_t = (R, H_<t, C_<t)
Runtime state:   S_t = (Q_t, A_t, D_t)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Requirements:
    """R: Fixed optimization requirements.
    
    This is immutable once created.
    """
    target_type: str
    target_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    objective: dict[str, Any] = field(default_factory=lambda: {
        "metric": "latency_ms",
        "direction": "minimize",
        "min_speedup": 1.05,
    })
    promotion: dict[str, Any] = field(default_factory=lambda: {
        "allowed": False,
        "require_correctness": True,
        "require_dispatch_diagnosis": True,
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "parameters": dict(self.parameters),
            "constraints": dict(self.constraints),
            "objective": dict(self.objective),
            "promotion": dict(self.promotion),
        }


@dataclass
class Hypothesis:
    """H: Optimization hypothesis.
    
    A falsifiable proposal for why a candidate should improve performance.
    """
    id: str
    target_keys: list[str] = field(default_factory=list)
    claim: str = ""  # What do we think is wrong?
    proposed_change: str = ""  # What change do we propose?
    expected_effect: str = ""  # Measurable expected outcome
    risk: str = ""  # What could go wrong?
    files_expected: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_keys": list(self.target_keys),
            "claim": self.claim,
            "proposed_change": self.proposed_change,
            "expected_effect": self.expected_effect,
            "risk": self.risk,
            "files_expected": list(self.files_expected),
            "stop_conditions": list(self.stop_conditions),
            "metadata": dict(self.metadata),
        }


@dataclass
class Artifact:
    """B: Implementation artifact.
    
    Concrete output from a hypothesis. Must be isolated.
    """
    hypothesis_id: str
    artifact_type: str  # "patch", "worktree", "declare_only", "parametric"
    changed_files: list[str] = field(default_factory=list)
    candidate_specs: list[str] = field(default_factory=list)
    patch_path: str | None = None
    registry_policy: str = "declare_only"  # "declare_only" or "publish"
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "artifact_type": self.artifact_type,
            "changed_files": list(self.changed_files),
            "candidate_specs": list(self.candidate_specs),
            "patch_path": self.patch_path,
            "registry_policy": self.registry_policy,
            "notes": self.notes,
            "metadata": dict(self.metadata),
        }


@dataclass
class EvidenceRecord:
    """C: Evaluation evidence.
    
    The core of the architecture. All decisions are based on evidence.
    """
    hypothesis_id: str
    artifact_id: str
    candidate_spec: str = ""
    baseline_spec: str = ""
    dispatch_keys: list[list[str]] = field(default_factory=list)
    correctness: str = "unknown"  # "passed", "failed", "unknown"
    eligible: bool = False
    mean_ms_candidate: float | None = None
    mean_ms_baseline: float | None = None
    speedup: float | None = None
    regressions: list[str] = field(default_factory=list)
    failure_reason: str = ""
    decision_recommendation: str = "inconclusive"  # "accepted", "rejected", etc.
    raw_output: str = ""  # Path to raw benchmark output
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "artifact_id": self.artifact_id,
            "candidate_spec": self.candidate_spec,
            "baseline_spec": self.baseline_spec,
            "dispatch_keys": [list(k) for k in self.dispatch_keys],
            "correctness": self.correctness,
            "eligible": self.eligible,
            "mean_ms_candidate": self.mean_ms_candidate,
            "mean_ms_baseline": self.mean_ms_baseline,
            "speedup": self.speedup,
            "regressions": list(self.regressions),
            "failure_reason": self.failure_reason,
            "decision_recommendation": self.decision_recommendation,
            "raw_output": self.raw_output,
            "metadata": dict(self.metadata),
        }


@dataclass
class WorkItem:
    """Runtime work item for queue tracking."""
    id: str
    phase: str  # "hypothesis", "artifact", "evaluation"
    status: str = "pending"  # "pending", "active", "done", "failed"
    hypothesis_id: str | None = None
    artifact_id: str | None = None
    result_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AlgorithmState:
    """X_t = (R, H_<t, C_<t): Algorithm state."""
    requirements: Requirements
    hypotheses: list[Hypothesis] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    round_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirements": self.requirements.to_dict(),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "evidence": [e.to_dict() for e in self.evidence],
            "round_index": self.round_index,
        }


@dataclass
class RuntimeState:
    """S_t = (Q_t, A_t, D_t): Runtime state."""
    queue: list[WorkItem] = field(default_factory=list)
    active: list[WorkItem] = field(default_factory=list)
    done: list[WorkItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue": len(self.queue),
            "active": len(self.active),
            "done": len(self.done),
        }


@dataclass
class OptimizerState:
    """Combined state for the optimizer."""
    algorithm: AlgorithmState
    runtime: RuntimeState = field(default_factory=lambda: RuntimeState())
    work_dir: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm.to_dict(),
            "runtime": self.runtime.to_dict(),
            "work_dir": str(self.work_dir) if self.work_dir else None,
        }

    def advance(self, new_hypotheses: list[Hypothesis], new_evidence: list[EvidenceRecord]) -> OptimizerState:
        """Create next state X_{t+1} = (R, H_≤t, C_≤t)."""
        return OptimizerState(
            algorithm=AlgorithmState(
                requirements=self.algorithm.requirements,
                hypotheses=self.algorithm.hypotheses + new_hypotheses,
                evidence=self.algorithm.evidence + new_evidence,
                round_index=self.algorithm.round_index + 1,
            ),
            runtime=RuntimeState(),  # Fresh runtime state for new round
            work_dir=self.work_dir,
        )
