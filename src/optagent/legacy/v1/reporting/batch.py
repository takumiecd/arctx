"""Batch optimization reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from optagent.legacy.v1.core.models import Decision, Requirement
from optagent.legacy.v1.core.state import OptimizationState


@dataclass
class BatchResult:
    """Result of a single optimization in a batch."""
    requirement_id: str
    requirement: Requirement
    state: OptimizationState | None = None
    success: bool = False
    error: str | None = None
    duration_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        decision = None
        if self.state:
            # Current workflow state compatibility
            if hasattr(self.state, 'algorithm') and self.state.algorithm.evidence:
                last_ev = self.state.algorithm.evidence[-1]
                decision = getattr(last_ev, 'decision_recommendation', None)
            # v1.5 compatibility
            elif hasattr(self.state, 'decisions') and self.state.decisions:
                decision = self.state.decisions[-1].to_dict()
        
        return {
            "requirement_id": self.requirement_id,
            "requirement": self.requirement.to_dict(),
            "success": self.success,
            "error": self.error,
            "duration_sec": self.duration_sec,
            "state_path": str(self.state.work_dir) if self.state else None,
            "decision": decision,
        }


@dataclass
class BatchReport:
    """Aggregated report for batch optimization."""
    results: list[BatchResult] = field(default_factory=list)
    total: int = 0
    successful: int = 0
    failed: int = 0
    accepted: int = 0
    rejected: int = 0
    best_speedup: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total": self.total,
                "successful": self.successful,
                "failed": self.failed,
                "accepted": self.accepted,
                "rejected": self.rejected,
                "best_speedup": self.best_speedup,
            },
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            "# Optimization Batch Report",
            "",
            "## Summary",
            "",
            f"- **Total**: {self.total}",
            f"- **Successful**: {self.successful}",
            f"- **Failed**: {self.failed}",
            f"- **Accepted**: {self.accepted}",
            f"- **Rejected**: {self.rejected}",
        ]
        if self.best_speedup is not None:
            lines.append(f"- **Best Speedup**: {self.best_speedup:.2f}x")
        lines.append("")

        lines.append("## Results")
        lines.append("")
        for result in self.results:
            status = "✅" if result.success else "❌"
            lines.append(f"### {status} {result.requirement_id}")
            lines.append(f"- **Type**: {result.requirement.target_type}")
            lines.append(f"- **Duration**: {result.duration_sec:.1f}s")
            
            if result.success and result.state:
                # Current workflow state compatibility
                if hasattr(result.state, 'algorithm') and result.state.algorithm.evidence:
                    last_ev = result.state.algorithm.evidence[-1]
                    decision_rec = getattr(last_ev, 'decision_recommendation', 'unknown')
                    lines.append(f"- **Decision**: {decision_rec}")
                # v1.5 compatibility
                elif hasattr(result.state, 'decisions') and result.state.decisions:
                    decision = result.state.decisions[-1]
                    lines.append(f"- **Decision**: {'Accepted' if decision.accepted else 'Rejected'}")
                    if decision.reason:
                        lines.append(f"- **Reason**: {decision.reason}")
            elif result.error:
                lines.append(f"- **Error**: {result.error}")
            lines.append("")

        return "\n".join(lines)

    def save(self, work_dir: Path, filename: str = "batch_report") -> Path:
        """Save report in JSON and Markdown formats."""
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        
        json_path = work_dir / f"{filename}.json"
        json_path.write_text(self.to_json(), encoding="utf-8")
        
        md_path = work_dir / f"{filename}.md"
        md_path.write_text(self.to_markdown(), encoding="utf-8")
        
        return json_path
