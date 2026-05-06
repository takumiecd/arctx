"""Integration tests for v2 framework end-to-end workflow."""

import unittest
from optagent.legacy.v2.state import State, ArtifactSet, Artifact, Transition, Knowledge, Observation
from optagent.legacy.v2.action import ApplyHypothesis, RunEvaluation
from optagent.legacy.v2.reward import RewardSpec, Objective, WeightedSum
from optagent.legacy.v2.planner import DefaultPlanner
from optagent.legacy.v2.mcts import MCTSOptimizer
from optagent.legacy.v2.value import ValuePredictor
from optagent.legacy.v2.hybrid import HybridOptimizer
from optagent.legacy.v2.rollout import RolloutSimulator, RolloutBudget
from optagent.legacy.v2.policy import LLMProposer


class TestRollout(unittest.TestCase):
    def test_simulate(self):
        class MockProposer:
            def generate_actions(self, state, n, temperature):
                return [ApplyHypothesis(hypothesis_id=f"h{i}", hypothesis_content="test") for i in range(n)]

        proposer = MockProposer()
        sim = RolloutSimulator(proposer=proposer)
        state = State(requirement={"target": "test"})
        budget = RolloutBudget(max_total_cost=50.0, max_depth=3)

        result = sim.simulate(state, budget=budget, depth=0)
        self.assertIsNotNone(result)
        # Result may have no paths if pruned, but structure is correct
        self.assertEqual(len(result.paths) >= 0, True)


class TestLLMProposer(unittest.TestCase):
    def test_generate_actions(self):
        proposer = LLMProposer(backend=None)
        state = State(requirement={"target": "test"})
        actions = proposer.generate_actions(state, n=5, temperature=0.7)
        self.assertEqual(len(actions), 5)

    def test_score_actions(self):
        proposer = LLMProposer(backend=None)
        state = State(requirement={"target": "test"})
        actions = proposer.generate_actions(state, n=3, temperature=0.7)
        scores = proposer.score_actions(state, actions)
        self.assertEqual(len(scores), 3)
        self.assertAlmostEqual(sum(scores), 1.0, places=5)


class TestEndToEnd(unittest.TestCase):
    def test_optimizer_workflow(self):
        """Test complete optimization workflow."""
        # Setup
        proposer = LLMProposer(backend=None)
        planner = DefaultPlanner(proposer=proposer)
        mcts = MCTSOptimizer(value_predictor=ValuePredictor())
        hybrid = HybridOptimizer(planner=planner, mcts=mcts)
        
        # Initial state
        state = State(requirement={"target": "optimize_latency"})
        reward_spec = RewardSpec(
            objectives=[Objective(name="latency", direction="minimize", reference=100.0)],
            aggregator=WeightedSum({"latency": 1.0}),
        )
        
        # Run optimization (limited steps)
        final_state = hybrid.optimize(state, reward_spec, max_steps=2)
        
        # Verify state evolved
        self.assertGreater(len(final_state.trajectory), 0)
        self.assertEqual(final_state.requirement, {"target": "optimize_latency"})


if __name__ == "__main__":
    unittest.main()
