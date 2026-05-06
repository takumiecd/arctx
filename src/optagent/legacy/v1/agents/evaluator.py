"""Evaluation agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from optagent.legacy.v1.core.state_model import EvidenceRecord
from optagent.legacy.v1.protocol import WorkItemDir


class EvaluatorAgent:
    """Evaluates artifacts for correctness and performance.
    
    Modes:
    - HarnessEvaluator: Use kernel harness and benchmark suites
    - BuildEvaluator: Build native extensions
    - NsightEvaluator: Profiler integration (future)
    - SimulationEvaluator: Triage only, not for promotion
    """

    def __init__(self, mode: str = "harness") -> None:
        self.mode = mode

    def evaluate(self, work_item: WorkItemDir) -> EvidenceRecord:
        """Evaluate artifact."""
        request = work_item.read_request()
        artifact = request["artifact"]
        requirements = request["requirements"]
        
        # Mock evaluation
        evidence = EvidenceRecord(
            hypothesis_id=artifact["hypothesis_id"],
            artifact_id=artifact["artifact_type"],
            candidate_spec=artifact["candidate_specs"][0] if artifact["candidate_specs"] else "",
            baseline_spec="baseline",
            correctness="passed",
            eligible=True,
            mean_ms_candidate=0.8,
            mean_ms_baseline=1.0,
            speedup=1.25,
            decision_recommendation="accepted",
            raw_output=str(work_item.logs_dir / "benchmark.jsonl"),
        )
        
        work_item.write_response(evidence.to_dict())
        return evidence
