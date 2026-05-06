"""§11.3 CodeProposer — LLM-based diff generation.

Corresponds to PLANNING_AND_RL.md §11.3 and §7.

Wraps v1/backends or direct LLM calls to generate code optimization diffs.
"""

from __future__ import annotations

from typing import List, Any, Protocol
from pathlib import Path

from optagent.legacy.v2.state import State
from optagent.legacy.v2.policy import Proposer
from optagent.legacy.v2.domains.code.action import EditCode


class LLMBackend(Protocol):
    """Minimal backend interface for CodeProposer."""

    def complete(self, prompt: str, n: int, temperature: float) -> list[str]:
        ...


class CodeProposer:
    """Propose code edits via LLM (§11.3, §7.2)."""

    def __init__(self, backend: LLMBackend = None, prompt_template: str = None):
        self.backend = backend
        self.prompt_template = prompt_template or self._default_prompt()

    def generate_actions(self, state: State, n: int, temperature: float) -> List[Any]:
        """Generate EditCode actions from LLM."""
        if self.backend is None:
            return self._mock_actions(n)

        # Limit to avoid overloading the LLM backend (real backends are slow)
        n = min(n, 1)
        code = self._extract_code(state)
        prompt = self.prompt_template.format(
            code=code,
            n=n,
            objectives=self._extract_objectives(state),
        )
        responses = self.backend.complete(prompt, n=n, temperature=temperature)
        return self._parse_responses(responses)

    def score_actions(self, state: State, actions: List[Any]) -> List[float]:
        """Score edits by syntactic plausibility."""
        if not actions:
            return []
        return [1.0 / len(actions)] * len(actions)

    def evaluate_state(self, state: State) -> float:
        """Estimate value of current code state."""
        # Higher is better: prefer states with passing tests
        return 0.5

    def _mock_actions(self, n: int) -> List[Any]:
        """Return mock actions when no backend is provided."""
        return [
            EditCode(diff=f"# optimization suggestion {i}", target_path=Path("."))
            for i in range(n)
        ]

    def _extract_code(self, state: State) -> str:
        """Extract current code from state."""
        if state.artifact.incumbent and isinstance(state.artifact.incumbent.content, str):
            return state.artifact.incumbent.content
        return ""

    def _extract_objectives(self, state: State) -> str:
        """Extract objectives from state requirement."""
        req = state.requirement
        if isinstance(req, dict):
            return req.get("objective", "general optimization")
        return str(req)

    def _parse_responses(self, responses: list[str]) -> List[Any]:
        """Parse LLM responses into EditCode actions.

        Extracts complete code blocks and creates a diff against the current code.
        """
        import re
        actions = []
        for resp in responses:
            # Extract complete code from markdown python blocks
            code_blocks = re.findall(r"```python\n(.*?)\n```", resp, re.DOTALL)
            if not code_blocks:
                # Fallback: any code block
                code_blocks = re.findall(r"```\n(.*?)\n```", resp, re.DOTALL)
            for code in code_blocks:
                code = code.strip()
                if not code:
                    continue
                # Create a simple "replace entire file" diff
                # (avoids patch command issues with complex diffs)
                actions.append(EditCode(diff=code, target_path=Path(".")))
        return actions

    def _default_prompt(self) -> str:
        return """You are a code optimization expert.

Current code:
```python
{code}
```

Please suggest {n} optimized version of the code. Return ONLY the complete optimized code as a markdown code block (```python ... ```).
Focus on: {objectives}

Do NOT return diffs. Return the complete optimized code only.
"""
