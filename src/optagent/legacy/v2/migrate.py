"""Phase 7: Migration utilities from v1.5 to v2."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from optagent.legacy.v1.core.manager import ManagerAgent as ManagerAgentV1
from optagent.legacy.v1.core.state_model import OptimizerState
from optagent.legacy.v2.state import State
from optagent.legacy.v2.bridge import state_v1_to_v2, state_v2_to_v1
from optagent.legacy.v2.planner import DefaultPlanner
from optagent.legacy.v2.mcts import MCTSOptimizer
from optagent.legacy.v2.value import ValuePredictor
from optagent.legacy.v2.hybrid import HybridOptimizer
from optagent.legacy.v2.policy import LLMProposer


class MigrationHelper:
    """Helper for migrating from v1.5 to v2."""

    def __init__(self, work_dir: str | Path):
        self.work_dir = Path(work_dir)

    def convert_state_file(self, v1_path: Path) -> State:
        """Convert v1.5 state file to v2 State."""
        v1_state = OptimizerState.from_file(v1_path)
        return state_v1_to_v2(v1_state)

    def create_v2_optimizer(self, backend=None) -> HybridOptimizer:
        """Create a v2 HybridOptimizer with default components."""
        proposer = LLMProposer(backend=backend)
        planner = DefaultPlanner(proposer=proposer, value_predictor=ValuePredictor())
        mcts = MCTSOptimizer(value_predictor=ValuePredictor())
        return HybridOptimizer(planner=planner, mcts=mcts)

    def run_migration_test(self, v1_state_path: Path) -> bool:
        """Test migration round-trip."""
        try:
            # v1 -> v2
            v2_state = self.convert_state_file(v1_state_path)
            
            # v2 -> v1
            v1_state = state_v2_to_v1(v2_state)
            
            # Verify
            assert v1_state.algorithm.round_index == len(v2_state.trajectory)
            return True
        except Exception as e:
            print(f"Migration test failed: {e}")
            return False
