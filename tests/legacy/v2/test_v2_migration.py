"""Tests for v2 migration utilities."""

import unittest
import tempfile
from pathlib import Path

from optagent.legacy.v1.core.state_model import OptimizerState, AlgorithmState, Requirements
from optagent.legacy.v2.migrate import MigrationHelper
from optagent.legacy.v2.bridge import state_v1_to_v2, state_v2_to_v1


class TestMigration(unittest.TestCase):
    def test_round_trip(self):
        req = Requirements(target_type="kernel", target_id="test")
        v1_state = OptimizerState(algorithm=AlgorithmState(requirements=req))
        
        # v1 -> v2
        v2_state = state_v1_to_v2(v1_state)
        self.assertIsNotNone(v2_state)
        
        # v2 -> v1
        v1_state_back = state_v2_to_v1(v2_state)
        self.assertEqual(v1_state_back.algorithm.round_index, 0)

    def test_migration_helper(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            helper = MigrationHelper(work_dir=tmpdir)
            optimizer = helper.create_v2_optimizer(backend=None)
            self.assertIsNotNone(optimizer)


if __name__ == "__main__":
    unittest.main()
