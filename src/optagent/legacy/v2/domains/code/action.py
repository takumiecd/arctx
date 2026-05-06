"""§11.3 Action instantiation — EditCode, RunTests, RunBenchmark.

Corresponds to PLANNING_AND_RL.md §11.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from pathlib import Path

from optagent.legacy.v2.state import Artifact, State
from optagent.legacy.v2.action import Action


@dataclass
class EditCode:
    """Action: apply a diff to code (§11.3)."""
    diff: str  # Unified diff or patch
    target_path: Optional[Path] = None
    cost_model: Optional[Any] = None

    def apply(self, state: State) -> Artifact:
        """Apply diff and produce new artifact."""
        # TODO: apply diff to file
        metadata = {
            "diff": self.diff,
            "target_path": str(self.target_path) if self.target_path else None,
        }
        return Artifact(
            artifact_id=f"edit_{hash(self.diff) & 0xFFFFFFFF:08x}",
            content=self.diff,
            metadata=metadata,
        )

    def cost(self, state: State) -> float:
        """Cost of applying a diff is low."""
        return 1.0

    def observability(self) -> dict[str, str]:
        return {"code": "patched_code"}


@dataclass
class RunTests:
    """Action: run test suite for current code."""
    test_command: str = "pytest"
    target_path: Optional[Path] = None
    cost_model: Optional[Any] = None

    def apply(self, state: State) -> Artifact:
        """Produce artifact with test results."""
        # TODO: execute tests
        return Artifact(
            artifact_id=f"test_{hash(self.test_command) & 0xFFFFFFFF:08x}",
            content=None,
            metadata={"test_command": self.test_command},
        )

    def cost(self, state: State) -> float:
        """Test execution is moderately expensive."""
        return 5.0

    def observability(self) -> dict[str, str]:
        return {"test_results": "pass/fail"}


@dataclass
class RunBenchmark:
    """Action: benchmark current code for performance metrics."""
    benchmark_command: str = "python -m timeit"
    iterations: int = 5
    cost_model: Optional[Any] = None

    def apply(self, state: State) -> Artifact:
        """Produce artifact with benchmark results."""
        # TODO: execute benchmark
        return Artifact(
            artifact_id=f"bench_{hash(self.benchmark_command) & 0xFFFFFFFF:08x}",
            content=None,
            metadata={"benchmark_command": self.benchmark_command, "iterations": self.iterations},
        )

    def cost(self, state: State) -> float:
        """Benchmarking is expensive."""
        return 10.0

    def observability(self) -> dict[str, str]:
        return {"metrics": "latency,memory"}
