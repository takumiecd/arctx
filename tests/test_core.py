"""Tests for core optimization engine."""

import tempfile
import unittest
from pathlib import Path

from optagent.core.manager import ManagerAgent
from optagent.core.models import (
    Artifact,
    Decision,
    Evidence,
    Hypothesis,
    OptimizationConfig,
    Requirement,
)
from optagent.core.state import OptimizationState
from optagent.backends.mock import MockBackend
from optagent.evaluation.base import Evaluator
from optagent.strategies.base import Strategy


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
            strategy=strategy,
            backend=backend,
            evaluator=evaluator,
            work_dir=self.work_dir,
        )
        
        req = Requirement(
            target_type="test",
            target_id="test_1",
            parameters={"key": "value"},
        )
        
        state = agent.optimize(req)
        
        self.assertEqual(state.round_index, 1)
        self.assertEqual(state.requirement, req)
        self.assertEqual(len(state.hypotheses), 1)
        self.assertEqual(len(state.artifacts), 1)
        self.assertEqual(len(state.evidence), 1)
        self.assertEqual(len(state.decisions), 1)
        
        # Decision should be accepted (speedup 1.5 > target 1.05)
        decision = state.decisions[0]
        self.assertTrue(decision.accepted)

    def test_state_persistence(self):
        """State should be saved to disk after optimization."""
        backend = MockBackend()
        strategy = MockStrategy()
        evaluator = MockEvaluator()
        
        agent = ManagerAgent(
            strategy=strategy,
            backend=backend,
            evaluator=evaluator,
            work_dir=self.work_dir,
        )
        
        req = Requirement(target_type="test", target_id="test_1")
        state = agent.optimize(req)
        
        state_file = self.work_dir / "state_round_1.json"
        self.assertTrue(state_file.exists())
        
        # Should be loadable
        loaded = OptimizationState.from_file(state_file)
        self.assertEqual(loaded.round_index, 1)

    def test_multiple_rounds(self):
        """Multiple optimization rounds should increment round_index."""
        backend = MockBackend()
        strategy = MockStrategy()
        evaluator = MockEvaluator()
        
        agent = ManagerAgent(
            strategy=strategy,
            backend=backend,
            evaluator=evaluator,
            work_dir=self.work_dir,
        )
        
        req = Requirement(target_type="test", target_id="test_1")
        
        state1 = agent.optimize(req)
        state2 = agent.optimize(req, state=state1)
        
        self.assertEqual(state2.round_index, 2)


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
