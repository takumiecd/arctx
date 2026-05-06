"""Tests for v2 framework core modules."""

import unittest
from optagent.legacy.v2.state import State, ArtifactSet, Artifact, Transition, Knowledge, Observation
from optagent.legacy.v2.action import ApplyHypothesis, RunEvaluation
from optagent.legacy.v2.reward import RewardSpec, Objective, Constraint, WeightedSum, Lexicographic
from optagent.legacy.v2.planner import DefaultPlanner, Plan, PlannedStep
from optagent.legacy.v2.mcts import MCTSOptimizer, MCTSNode
from optagent.legacy.v2.value import ValuePredictor
from optagent.legacy.v2.hybrid import HybridOptimizer
from optagent.legacy.v2.bridge import state_v1_to_v2, state_v2_to_v1
from optagent.legacy.v1.core.state_model import OptimizerState, AlgorithmState, Requirements


class TestState(unittest.TestCase):
    def test_initial_state(self):
        req = {"target": "test"}
        state = State(requirement=req)
        self.assertEqual(state.requirement, req)
        self.assertEqual(len(state.trajectory), 0)
        self.assertEqual(len(state.artifact.candidates), 0)

    def test_artifact_set(self):
        art = Artifact(artifact_id="a1", content="test")
        art_set = ArtifactSet(candidates=[art])
        self.assertEqual(len(art_set.candidates), 1)


class TestAction(unittest.TestCase):
    def test_apply_hypothesis(self):
        state = State(requirement={"target": "test"})
        action = ApplyHypothesis(hypothesis_id="h1", hypothesis_content="optimize loop")
        artifact = action.apply(state)
        self.assertEqual(artifact.artifact_id, "h1")
        self.assertEqual(action.cost(state), 1.0)

    def test_run_evaluation(self):
        state = State(requirement={"target": "test"})
        action = RunEvaluation(artifact_id="a1")
        self.assertEqual(action.cost(state), 5.0)


class TestReward(unittest.TestCase):
    def test_objective_improvement(self):
        obj = Objective(name="latency", direction="minimize", reference=100.0)
        self.assertEqual(obj.compute_improvement(50.0), 2.0)

    def test_weighted_sum(self):
        agg = WeightedSum({"speed": 0.7, "memory": 0.3})
        score = agg.aggregate({"speed": 1.5, "memory": 0.8})
        self.assertAlmostEqual(score, 1.29, places=2)

    def test_lexicographic(self):
        agg = Lexicographic(["correctness", "speed"])
        score = agg.aggregate({"correctness": 1.0, "speed": 1.5})
        self.assertEqual(score, (1.0, 1.5))


class TestPlanner(unittest.TestCase):
    def test_plan_creation(self):
        class MockProposer:
            def generate_actions(self, state, n, temperature):
                return [ApplyHypothesis(hypothesis_id=f"h{i}", hypothesis_content="test") for i in range(3)]

        planner = DefaultPlanner(proposer=MockProposer())
        state = State(requirement={"target": "test"})
        reward_spec = RewardSpec()
        plan = planner.create_plan(state, reward_spec, horizon=3)
        self.assertEqual(len(plan.steps), 3)

    def test_plan_execution(self):
        action = ApplyHypothesis(hypothesis_id="h1", hypothesis_content="test")
        plan = Plan(steps=[])
        self.assertTrue(plan.is_complete())


class TestMCTS(unittest.TestCase):
    def test_ucb_unvisited(self):
        node = MCTSNode(state=State(requirement={}))
        self.assertEqual(node.ucb(10), float('inf'))

    def test_ucb_visited(self):
        node = MCTSNode(state=State(requirement={}))
        node.visit_count = 5
        node.value_sum = 10.0
        ucb = node.ucb(20, c=1.414)
        # exploitation=2.0, exploration ~1.26 (ln(20)/5)^0.5 * c
        self.assertGreater(ucb, 1.0)
        self.assertGreater(ucb, 2.0)  # exploitation alone is 2.0

    def test_mcts_search(self):
        class MockProposer:
            def generate_actions(self, state, n, temperature):
                return [ApplyHypothesis(hypothesis_id=f"h{i}", hypothesis_content="test") for i in range(3)]

            def score_actions(self, state, actions):
                return [1.0 / len(actions)] * len(actions) if actions else []

        mcts = MCTSOptimizer()
        state = State(requirement={"target": "test"})
        proposer = MockProposer()
        action = mcts.search(state, proposer, n_simulations=10)
        self.assertIsNotNone(action)


class TestValuePredictor(unittest.TestCase):
    def test_prediction(self):
        predictor = ValuePredictor()
        state = State(requirement={"target": "test"})
        action = ApplyHypothesis(hypothesis_id="h1", hypothesis_content="test")
        value = predictor.predict(action, state)
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 1.0)


class TestBridge(unittest.TestCase):
    def test_v1_to_v2(self):
        req = Requirements(target_type="kernel", target_id="test")
        v1_state = OptimizerState(algorithm=AlgorithmState(requirements=req))
        v2_state = state_v1_to_v2(v1_state)
        self.assertIsNotNone(v2_state)
        self.assertEqual(v2_state.requirement, req)

    def test_v2_to_v1(self):
        v2_state = State(requirement=Requirements(target_type="test", target_id="test"))
        v1_state = state_v2_to_v1(v2_state)
        self.assertIsNotNone(v1_state)


if __name__ == "__main__":
    unittest.main()
