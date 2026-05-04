"""Tests for batch optimization."""

import tempfile
import unittest
from pathlib import Path

from optagent.batch import BatchOptimizer
from optagent.core.manager import ManagerAgent
from optagent.core.models import Requirement, OptimizationConfig
from optagent.backends.mock import MockBackend
from optagent.evaluation.base import Evaluator
from optagent.strategies.base import Strategy
from optagent.core.models import Evidence


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


class TestBatchOptimizer(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _make_factory(self):
        def factory():
            return ManagerAgent(
                strategy=MockStrategy(),
                backend=MockBackend(hypotheses=[]),
                evaluator=MockEvaluator(),
                work_dir=".",
            )
        return factory

    def test_batch_runs_multiple(self):
        """BatchOptimizer should process multiple requirements."""
        optimizer = BatchOptimizer(
            manager_factory=self._make_factory(),
            work_dir=self.work_dir,
            max_workers=1,
        )
        
        requirements = [
            ("req_1", Requirement(target_type="kernel", target_id="k1")),
            ("req_2", Requirement(target_type="kernel", target_id="k2")),
        ]
        
        report = optimizer.run(requirements, resume=False)
        
        self.assertEqual(report.total, 2)
        self.assertEqual(len(report.results), 2)

    def test_batch_report_generation(self):
        """Batch report should be generated correctly."""
        optimizer = BatchOptimizer(
            manager_factory=self._make_factory(),
            work_dir=self.work_dir,
            max_workers=1,
        )
        
        requirements = [
            ("req_1", Requirement(target_type="kernel", target_id="k1")),
        ]
        
        report = optimizer.run(requirements, resume=False)
        
        # Save report
        json_path = report.save(self.work_dir, "test_report")
        self.assertTrue(json_path.exists())
        self.assertTrue((self.work_dir / "test_report.md").exists())
        
        # Verify JSON content
        import json
        data = json.loads(json_path.read_text())
        self.assertEqual(data["summary"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
