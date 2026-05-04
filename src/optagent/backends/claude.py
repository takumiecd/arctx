"""Claude Code backend integration."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from optagent.backends.base import Backend
from optagent.core.models import Artifact, Hypothesis
from optagent.core.state import OptimizationState


CLAUDE_PROMPT_TEMPLATE = """\
You are an expert optimization engineer with deep knowledge of performance engineering.

## Target

- Type: {target_type}
- ID: {target_id}
- Objective: {objective}

## Context

{context}

## Task

Analyze the target and propose an optimized version.
Focus on:
1. Algorithmic improvements
2. Memory access patterns
3. Parallelization opportunities
4. Numerical stability

Output ONLY a markdown code block with the optimized implementation.
Include the target file path on the first line as a comment.

```python
# {output_file}
# Your optimized implementation here
```
"""


class ClaudeBackend(Backend):
    """Backend that uses Claude Code CLI for optimization.

    Parameters
    ----------
    command:
        Path to the ``claude`` executable.
    model:
        Model selector.
    prompt_template:
        Template for building prompts.
    timeout:
        Maximum seconds to wait.
    max_tokens:
        Maximum tokens in response.
    """

    def __init__(
        self,
        command: str | Path = "claude",
        model: str = "claude-sonnet-4-20250514",
        prompt_template: str = CLAUDE_PROMPT_TEMPLATE,
        timeout: float = 600.0,
        max_tokens: int = 8000,
    ) -> None:
        self.command = Path(command)
        self.model = model
        self.prompt_template = prompt_template
        self.timeout = timeout
        self.max_tokens = max_tokens

    def propose_hypotheses(
        self,
        state: OptimizationState,
        analysis: dict[str, Any],
    ) -> list[Hypothesis]:
        return [
            Hypothesis(
                id=f"hyp_{state.round_index}_claude_0",
                description=f"Claude optimization for {state.requirement.target_id if state.requirement else 'unknown'}",
                strategy_type="claude",
                confidence=0.85,
            )
        ]

    def generate_artifact(
        self,
        hypothesis: Hypothesis,
        state: OptimizationState,
    ) -> Artifact:
        if state.requirement is None:
            raise RuntimeError("ClaudeBackend: requirement is required")

        prompt = self._build_prompt(hypothesis, state)
        output = self._run_claude(prompt)

        files = self._extract_files(output)

        return Artifact(
            hypothesis_id=hypothesis.id,
            artifact_type="code",
            content=output,
            files=tuple(files),
            metadata={"model": self.model, "prompt_length": len(prompt)},
        )

    def is_available(self) -> bool:
        try:
            subprocess.run(
                [str(self.command), "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _build_prompt(self, hypothesis: Hypothesis, state: OptimizationState) -> str:
        import json
        req = state.requirement
        if req is None:
            raise RuntimeError("No requirement in state")

        return self.prompt_template.format(
            target_type=req.target_type,
            target_id=req.target_id,
            objective=json.dumps(req.objective),
            context=json.dumps(req.parameters, indent=2),
            output_file=f"optimized_{req.target_id}.py",
        )

    def _run_claude(self, prompt: str) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(prompt)
            prompt_file = f.name

        cmd = [
            str(self.command),
            "--print",
            "--model",
            self.model,
            "--max-tokens",
            str(self.max_tokens),
            prompt_file,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Claude command not found: {self.command}") from exc
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude timed out after {self.timeout}s")
        finally:
            Path(prompt_file).unlink(missing_ok=True)

        if result.returncode != 0:
            raise RuntimeError(f"Claude failed: {result.stderr.strip()}")

        return result.stdout

    @staticmethod
    def _extract_files(output: str) -> list[str]:
        pattern = re.compile(r"```\w*\n#\s*(.+?)\n", re.MULTILINE)
        return pattern.findall(output)
