"""Tests for canonical Evidence Graph records and StateStore."""

import json
import tempfile
import unittest
from pathlib import Path

from optagent.core import (
    ActionRecord,
    ArtifactRecord,
    AttemptRecord,
    DecisionRecord,
    EvidenceRecord,
    FindingRecord,
    HypothesisRecord,
    ObservationRecord,
    RequirementRecord,
    StateStore,
)
from optagent.v1.core.manager import ManagerAgent
from optagent.v1.core.state_model import Requirements


class TestStateStore(unittest.TestCase):
    def test_append_attempt_writes_evidence_graph_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp), run_id="run_test")
            requirement = RequirementRecord(
                requirement_id="kernel:csc_linear",
                target_type="kernel",
                target_id="csc_linear",
            )
            store.save_requirement(requirement)

            attempt = AttemptRecord(
                attempt_id="attempt_0001",
                requirement_id=requirement.requirement_id,
                hypothesis=HypothesisRecord(
                    hypothesis_id="h1",
                    claim="small batch is launch-overhead bound",
                ),
                action=ActionRecord(
                    action_id="action:attempt_0001",
                    action_type="apply_hypothesis",
                ),
                artifact=ArtifactRecord(
                    artifact_id="artifact_0001",
                    artifact_type="patch",
                    path="artifacts/attempt_0001.patch",
                ),
                observation=ObservationRecord(
                    observation_id="observation:attempt_0001",
                    action_id="action:attempt_0001",
                    metrics={"speedup": 1.12},
                ),
                evidence=EvidenceRecord(
                    evidence_id="evidence:attempt_0001",
                    artifact_id="artifact_0001",
                    correctness="passed",
                    eligible=True,
                    speedup=1.12,
                ),
                decision=DecisionRecord(
                    decision_id="decision:attempt_0001",
                    status="accepted",
                    reason="Candidate passed promotion criteria.",
                ),
                finding=FindingRecord(
                    finding_id="finding:attempt_0001",
                    summary="Small-batch variant looks promising.",
                ),
            )
            store.append_attempt(attempt)

            attempts = store.read_attempts()
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0]["attempt_id"], "attempt_0001")
            self.assertTrue((Path(tmp) / "decisions.jsonl").exists())
            self.assertTrue((Path(tmp) / "findings.jsonl").exists())

            requirements = json.loads((Path(tmp) / "requirements.json").read_text())
            self.assertEqual(requirements["target_id"], "csc_linear")


class TestManagerEvidenceGraph(unittest.TestCase):
    def test_manager_records_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = ManagerAgent(work_dir=tmp)
            requirement = Requirements(
                target_type="kernel",
                target_id="csc_linear_forward",
                objective={
                    "metric": "latency_ms",
                    "direction": "minimize",
                    "min_speedup": 1.05,
                },
            )

            agent.optimize(requirement)

            attempts_path = Path(tmp) / "attempts.jsonl"
            self.assertTrue(attempts_path.exists())
            attempts = [json.loads(line) for line in attempts_path.read_text().splitlines()]
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0]["requirement_id"], "kernel:csc_linear_forward")
            self.assertEqual(attempts[0]["decision"]["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
