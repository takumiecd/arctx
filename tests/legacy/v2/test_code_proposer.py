"""Tests for v2 domains/code/ proposer."""

import unittest
from pathlib import Path

from optagent.legacy.v2.state import State, ArtifactSet, Artifact
from optagent.legacy.v2.domains.code.proposer import CodeProposer
from optagent.legacy.v2.domains.code.action import EditCode


class MockLLMBackend:
    """Mock backend that returns canned responses."""

    def __init__(self, responses: list[str] = None):
        self.responses = responses or []

    def complete(self, prompt: str, n: int, temperature: float) -> list[str]:
        return self.responses[:n]


class TestCodeProposer(unittest.TestCase):
    def test_mock_actions_without_backend(self):
        """Without backend, returns mock actions."""
        proposer = CodeProposer()
        state = State(requirement={"objective": "speed"})
        actions = proposer.generate_actions(state, n=3, temperature=0.7)
        self.assertEqual(len(actions), 3)
        for action in actions:
            self.assertIsInstance(action, EditCode)

    def test_generate_actions_with_backend(self):
        """With backend, parses LLM responses into actions."""
        backend = MockLLMBackend([
            "```python\ndef optimized():\n    return 'fast'\n```"
        ])
        proposer = CodeProposer(backend=backend)
        state = State(requirement={"objective": "speed"})
        state.artifact = ArtifactSet(
            incumbent=Artifact(artifact_id="test", content="x", metadata={})
        )
        actions = proposer.generate_actions(state, n=1, temperature=0.7)
        self.assertEqual(len(actions), 1)
        self.assertIn("fast", actions[0].diff)

    def test_extract_code_from_state(self):
        """Extract code from state incumbent."""
        proposer = CodeProposer()
        state = State(requirement={})
        state.artifact = ArtifactSet(
            incumbent=Artifact(artifact_id="test", content="print('hello')", metadata={})
        )
        code = proposer._extract_code(state)
        self.assertEqual(code, "print('hello')")

    def test_extract_objectives(self):
        """Extract objectives from state requirement."""
        proposer = CodeProposer()
        state = State(requirement={"objective": "minimize latency"})
        obj = proposer._extract_objectives(state)
        self.assertEqual(obj, "minimize latency")

    def test_score_actions(self):
        """Score actions returns uniform distribution."""
        proposer = CodeProposer()
        actions = [EditCode(diff="x"), EditCode(diff="y")]
        scores = proposer.score_actions(State(requirement={}), actions)
        self.assertEqual(len(scores), 2)
        self.assertAlmostEqual(scores[0], scores[1])


if __name__ == "__main__":
    unittest.main()
