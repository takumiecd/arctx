"""§11.3 Iterative Refinement — code optimization domain.

Corresponds to PLANNING_AND_RL.md §11.3.

Instantiates v2 swap points (§2/§3/§4) for code generation/refinement:
- artifact: current code state + test outcomes
- actions: EditCode(diff), RunTests(a), RunBenchmark(a)
- objectives: tests passing, no regressions
- aggregator: Lexicographic correctness ≫ test count ≫ style
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict
from pathlib import Path

from optagent.legacy.v2.state import State, ArtifactSet, Artifact, Transition, Knowledge, Observation
from optagent.legacy.v2.action import Action
from optagent.legacy.v2.reward import RewardSpec, Objective, Constraint, Lexicographic


@dataclass
class CodeArtifact:
    """Domain-specific artifact for code optimization."""
    artifact_id: str
    source_path: Path
    content: str  # Current code content
    test_results: Dict[str, Any] = field(default_factory=dict)
    benchmark_results: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeState:
    """§11.3 State instantiation: current code + test outcomes."""
    requirement: Any
    code: CodeArtifact
    history: List[Transition] = field(default_factory=list)
    knowledge: Knowledge = field(default_factory=Knowledge)

    def to_v2_state(self) -> State:
        """Convert to v2 generic State."""
        artifact = self._to_artifact(self.code)
        # Always set incumbent to current code (even if not tested yet)
        artifact_set = ArtifactSet(
            candidates=[artifact],
            pareto_front=[artifact] if self.code.test_results.get("passed") else [],
            incumbent=artifact,
        )
        return State(
            requirement=self.requirement,
            artifact=artifact_set,
            trajectory=self.history,
            knowledge=self.knowledge,
        )

    def _to_artifact(self, code: CodeArtifact) -> Artifact:
        return Artifact(
            artifact_id=code.artifact_id,
            content=code.content,
            metadata={
                "source_path": str(code.source_path),
                "test_results": code.test_results,
                "benchmark_results": code.benchmark_results,
                **code.metadata,
            },
        )

    @classmethod
    def from_v2_state(cls, state: State) -> "CodeState":
        """Restore from v2 generic State."""
        if not state.artifact.incumbent:
            raise ValueError("No incumbent in state")
        art = state.artifact.incumbent
        code = CodeArtifact(
            artifact_id=art.artifact_id,
            source_path=Path(art.metadata.get("source_path", "")),
            content=art.content,
            test_results=art.metadata.get("test_results", {}),
            benchmark_results=art.metadata.get("benchmark_results", {}),
            metadata={k: v for k, v in art.metadata.items() if k not in ("source_path", "test_results", "benchmark_results")},
        )
        return cls(
            requirement=state.requirement,
            code=code,
            history=state.trajectory,
            knowledge=state.knowledge,
        )
