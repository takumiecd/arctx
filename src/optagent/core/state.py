"""Optimization state management with persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from optagent.core.models import (
    Artifact,
    Decision,
    Evidence,
    Hypothesis,
    Requirement,
)


@dataclass
class OptimizationState:
    """Mutable state for an optimization session.
    
    Can be serialized to JSON for persistence and resume.
    """
    round_index: int = 0
    requirement: Requirement | None = None
    
    # Collected during workflow
    hypotheses: list[Hypothesis] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    
    # Metadata
    work_dir: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "requirement": self.requirement.to_dict() if self.requirement else None,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "artifacts": [a.to_dict() for a in self.artifacts],
            "evidence": [e.to_dict() for e in self.evidence],
            "decisions": [d.to_dict() for d in self.decisions],
            "metadata": dict(self.metadata),
        }

    def to_file(self, path: Path | str) -> None:
        """Serialize state to JSON file."""
        path = Path(path)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptimizationState:
        """Deserialize state from dict."""
        state = cls(
            round_index=data.get("round_index", 0),
            requirement=Requirement.from_dict(data["requirement"]) if data.get("requirement") else None,
            metadata=dict(data.get("metadata", {})),
        )
        # Note: full deserialization of hypotheses/artifacts/evidence/decisions
        # would require more complex logic - simplified here
        return state

    @classmethod
    def from_file(cls, path: Path | str) -> OptimizationState:
        """Deserialize state from JSON file."""
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)
