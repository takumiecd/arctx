"""Tests for core optimization engine (v2 compatible)."""

import tempfile
import unittest
from pathlib import Path

from optagent.legacy.v1.core.manager import ManagerAgent
from optagent.legacy.v1.core.models import (
    Artifact,
    Decision,
    Evidence,
    Hypothesis,
    OptimizationConfig,
    Requirement,
)
from optagent.legacy.v1.core.state import OptimizationState
from optagent.legacy.v1.backends.mock import MockBackend
from optagent.legacy.v1.evaluation.base import Evaluator
from optagent.legacy.v1.strategies.base import Strategy


class MockStrategy(Strategy):
    def initialize(self, state):
        pass

    def analyze(self, requirement):
        return {}

    def get_baseline(self, requirement):
        return {}

    def apply_changes(self, state):
        pass

    def validate_requirement(self, requirement):
        return True


class MockEvaluator(Evaluator):
    def evaluate(self, artifact, state):
        return Evidence(
            hypothesis_id=artifact.hypothesis_id,
            artifact_id=artifact.artifact_type,
            speedup=1.5,
            is_correct=True,
            is_eligible=True,
        )

    def is_available(self):
        return True


class TestManagerAgent(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_optimize_runs_full_workflow(self):
        """ManagerAgent should run complete optimization workflow."""
        backend = MockBackend(hypotheses=[
            Hypothesis(id="h1", description="test", strategy_type="mock")
        ])
        strategy = MockStrategy()
        evaluator = MockEvaluator()
        
        agent = ManagerAgent(
            work_dir=self.work_dir,
            strategy=strategy,
            backend=backend,
            evaluator=evaluator,
        )
        
        req = Requirement(
            target_type="test",
            target_id="test_1",
            parameters={"key": "value"},
        )
        
        # Use v2 interface
        from optagent.legacy.v1.core.state_model import Requirements as RequirementsV2
        req_v2 = RequirementsV2(
            target_type="test",
            target_id="test_1",
            parameters={"key": "value"},
        )
        
        state = agent.optimize(req_v2)
        
        # v2 state assertions
        self.assertEqual(state.algorithm.round_index, 0)  # First round is 0
        self.assertEqual(len(state.algorithm.hypotheses), 1)
        self.assertEqual(len(state.algorithm.evidence), 1)

    def test_state_persistence(self):
        """State should be saved to disk after optimization."""
        backend = MockBackend()
        strategy = MockStrategy()
        evaluator = MockEvaluator()
        
        agent = ManagerAgent(
            work_dir=self.work_dir,
            strategy=strategy,
            backend=backend,
            evaluator=evaluator,
        )
        
        from optagent.legacy.v1.core.state_model import Requirements as RequirementsV2
        req = RequirementsV2(target_type="test", target_id="test_1")
        state = agent.optimize(req)
        
        # v2 saves state as state_round_{index}.json
        state_file = self.work_dir / f"state_round_{state.algorithm.round_index}.json"
        self.assertTrue(state_file.exists())

    def test_multiple_rounds(self):
        """Multiple optimization rounds should increment round_index."""
        backend = MockBackend()
        strategy = MockStrategy()
        evaluator = MockEvaluator()
        
        agent = ManagerAgent(
            work_dir=self.work_dir,
            strategy=strategy,
            backend=backend,
            evaluator=evaluator,
        )
        
        from optagent.legacy.v1.core.state_model import Requirements as RequirementsV2
        req = RequirementsV2(target_type="test", target_id="test_1")
        
        state1 = agent.optimize(req)
        state2 = agent.optimize(req, state=state1)
        
        self.assertEqual(state2.algorithm.round_index, 1)  # Incremented by 1 from first round


class TestOptimizationState(unittest.TestCase):
    def test_serialization_roundtrip(self):
        """State should serialize and deserialize correctly."""
        state = OptimizationState(
            round_index=1,
            requirement=Requirement(target_type="test", target_id="t1"),
        )
        
        d = state.to_dict()
        self.assertEqual(d["round_index"], 1)
        self.assertEqual(d["requirement"]["target_type"], "test")


if __name__ == "__main__":
    unittest.main()
