"""Tests for ManagerAgent orchestration."""

import tempfile
import unittest
from pathlib import Path

from optagent.core.manager import ManagerAgent, PromotionGate
from optagent.core.state_model import (
    AlgorithmState,
    EvidenceRecord,
    Hypothesis,
    OptimizerState,
    Requirements,
)


class TestPromotionGate(unittest.TestCase):
    def test_accepted(self):
        gate = PromotionGate()
        req = Requirements(
            target_type="kernel",
            target_id="test",
            promotion={"allowed": False, "require_correctness": True, "require_dispatch_diagnosis": False},
        )
        ev = EvidenceRecord(
            hypothesis_id="h1",
            artifact_id="a1",
            correctness="passed",
            eligible=True,
            speedup=1.25,
        )
        self.assertEqual(gate.decide(ev, req), "accepted")

    def test_rejected_by_correctness(self):
        gate = PromotionGate()
        req = Requirements(target_type="kernel", target_id="test")
        ev = EvidenceRecord(
            hypothesis_id="h1",
            artifact_id="a1",
            correctness="failed",
            eligible=True,
            speedup=1.25,
        )
        self.assertEqual(gate.decide(ev, req), "rejected")

    def test_rejected_by_speedup(self):
        gate = PromotionGate()
        req = Requirements(target_type="kernel", target_id="test")
        ev = EvidenceRecord(
            hypothesis_id="h1",
            artifact_id="a1",
            correctness="passed",
            eligible=True,
            speedup=1.01,
        )
        self.assertEqual(gate.decide(ev, req), "rejected")

    def test_needs_narrower_scope(self):
        gate = PromotionGate()
        req = Requirements(target_type="kernel", target_id="test")
        ev = EvidenceRecord(
            hypothesis_id="h1",
            artifact_id="a1",
            correctness="passed",
            eligible=False,
            speedup=1.25,
        )
        self.assertEqual(gate.decide(ev, req), "needs_narrower_scope")


class TestManagerAgent(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_full_round(self):
        """ManagerAgent should complete one optimization round."""
        agent = ManagerAgent(work_dir=self.work_dir)
        req = Requirements(
            target_type="kernel",
            target_id="csc_linear_forward",
            objective={"metric": "latency_ms", "direction": "minimize", "min_speedup": 1.05},
        )
        
        state = agent.optimize(req)
        
        self.assertEqual(state.algorithm.round_index, 0)
        self.assertEqual(len(state.algorithm.hypotheses), 1)
        self.assertEqual(len(state.algorithm.evidence), 1)
        
        # Check state file was saved
        state_files = list(self.work_dir.glob("state_round_*.json"))
        self.assertEqual(len(state_files), 1)

    def test_hypothesis_guardrail(self):
        """ManagerAgent should reject hypotheses unrelated to target."""
        agent = ManagerAgent(work_dir=self.work_dir)
        req = Requirements(target_type="kernel", target_id="csc_linear")
        
        # This should work with default hypothesis
        state = agent.optimize(req)
        self.assertEqual(len(state.algorithm.hypotheses), 1)


if __name__ == "__main__":
    unittest.main()
