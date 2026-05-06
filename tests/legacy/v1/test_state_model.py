"""Tests for state model X_t = (R, H_<t, C_<t)."""

import unittest

from optagent.legacy.v1.core.state_model import (
    AlgorithmState,
    Artifact,
    EvidenceRecord,
    Hypothesis,
    OptimizerState,
    Requirements,
    RuntimeState,
    WorkItem,
)


class TestRequirements(unittest.TestCase):
    def test_immutable(self):
        """Requirements should be frozen/immutable."""
        r = Requirements(target_type="kernel", target_id="test")
        # dataclass(frozen=True) makes it immutable
        with self.assertRaises((AttributeError, TypeError)):
            r.target_type = "other"

    def test_to_dict(self):
        r = Requirements(target_type="kernel", target_id="csc_linear")
        d = r.to_dict()
        self.assertEqual(d["target_type"], "kernel")
        self.assertEqual(d["target_id"], "csc_linear")


class TestHypothesis(unittest.TestCase):
    def test_structure(self):
        h = Hypothesis(
            id="h_001",
            target_keys=["op:linear_forward"],
            claim="Generic path has overhead",
            proposed_change="Add specialized spec",
            expected_effect="1.2x speedup",
            risk="May regress small batches",
        )
        self.assertEqual(h.id, "h_001")
        self.assertIn("linear_forward", h.target_keys[0])

    def test_to_dict(self):
        h = Hypothesis(id="h_001", claim="test")
        d = h.to_dict()
        self.assertEqual(d["id"], "h_001")
        self.assertEqual(d["claim"], "test")


class TestArtifact(unittest.TestCase):
    def test_isolation(self):
        """Artifact must have registry_policy for isolation."""
        a = Artifact(
            hypothesis_id="h_001",
            artifact_type="patch",
            registry_policy="declare_only",
        )
        self.assertEqual(a.registry_policy, "declare_only")

    def test_no_publish_by_default(self):
        """Default should be declare_only, not publish."""
        a = Artifact(hypothesis_id="h_001", artifact_type="code")
        self.assertEqual(a.registry_policy, "declare_only")


class TestEvidenceRecord(unittest.TestCase):
    def test_complete_evidence(self):
        e = EvidenceRecord(
            hypothesis_id="h_001",
            artifact_id="patch",
            candidate_spec="spec_opt",
            baseline_spec="spec_base",
            dispatch_keys=[["op:linear_forward", "device:cuda"]],
            correctness="passed",
            eligible=True,
            speedup=1.25,
            decision_recommendation="accepted",
        )
        self.assertTrue(e.eligible)
        self.assertEqual(e.speedup, 1.25)


class TestAlgorithmState(unittest.TestCase):
    def test_initial_state(self):
        r = Requirements(target_type="kernel", target_id="test")
        state = AlgorithmState(requirements=r)
        self.assertEqual(state.round_index, 0)
        self.assertEqual(len(state.hypotheses), 0)
        self.assertEqual(len(state.evidence), 0)

    def test_state_transition(self):
        """X_t -> X_{t+1} via advance()."""
        r = Requirements(target_type="kernel", target_id="test")
        state = OptimizerState(algorithm=AlgorithmState(requirements=r))
        
        h = Hypothesis(id="h_1", claim="test")
        e = EvidenceRecord(hypothesis_id="h_1", artifact_id="a1", speedup=1.2)
        
        new_state = state.advance([h], [e])
        
        self.assertEqual(new_state.algorithm.round_index, 1)
        self.assertEqual(len(new_state.algorithm.hypotheses), 1)
        self.assertEqual(len(new_state.algorithm.evidence), 1)


class TestRuntimeState(unittest.TestCase):
    def test_queue_tracking(self):
        rt = RuntimeState()
        rt.queue.append(WorkItem(id="w1", phase="hypothesis"))
        self.assertEqual(len(rt.queue), 1)
        self.assertEqual(len(rt.active), 0)


if __name__ == "__main__":
    unittest.main()
