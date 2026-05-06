"""OpenCode backend integration."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from optagent.legacy.v1.backends.base import Backend
from optagent.legacy.v1.core.models import Artifact, Hypothesis
from optagent.legacy.v1.core.state import OptimizationState


DEFAULT_PROMPT_TEMPLATE = """\
You are an expert optimization engineer.

## Target

- Type: {target_type}
- ID: {target_id}
- Objective: {objective}

## Context

{context}

## Task

Propose an optimized version that improves performance while preserving correctness.

Rules:
1. Output ONLY the optimized code/configuration.
2. Include comments explaining key optimizations.
3. Do NOT use file-write tools.
4. Output as a markdown code block.

```python
# {output_file}
{content_hint}
```
"""


class OpenCodeBackend(Backend):
    """Backend that uses OpenCode CLI for optimization.

    Parameters
    ----------
    command:
        Path to the ``opencode`` executable.
    model:
        Model selector (e.g., "opencode-go/kimi-k2.6").
    prompt_template:
        Template for building prompts.
    timeout:
        Maximum seconds to wait.
    idle_timeout:
        Seconds without activity before abort.
    """

    def __init__(
        self,
        command: str | Path = "/home/jovyan/.opencode/bin/opencode",
        model: str = "opencode-go/kimi-k2.6",
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        timeout: float = 600.0,
        idle_timeout: float = 300.0,
    ) -> None:
        self.command = Path(command)
        self.model = model
        self.prompt_template = prompt_template
        self.timeout = timeout
        self.idle_timeout = idle_timeout

    def propose_hypotheses(
        self,
        state: OptimizationState,
        analysis: dict[str, Any],
    ) -> list[Hypothesis]:
        # For simplicity, generate one hypothesis per call.
        # Could be extended to generate multiple variants.
        return [
            Hypothesis(
                id=f"hyp_{state.round_index}_0",
                description=f"Optimize {state.requirement.target_id if state.requirement else 'unknown'}",
                strategy_type="opencode",
                confidence=0.8,
            )
        ]

    def generate_artifact(
        self,
        hypothesis: Hypothesis,
        state: OptimizationState,
    ) -> Artifact:
        if state.requirement is None:
            raise RuntimeError("OpenCodeBackend: requirement is required")

        prompt = self._build_prompt(hypothesis, state)
        output = self._run_opencode(prompt)

        # Extract code blocks
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
        req = state.requirement
        if req is None:
            raise RuntimeError("No requirement in state")
        
        return self.prompt_template.format(
            target_type=req.target_type,
            target_id=req.target_id,
            objective=json.dumps(req.objective),
            context=json.dumps(req.parameters, indent=2),
            output_file=f"optimized_{req.target_id}.py",
            content_hint="# Your optimized implementation here",
        )

    def _run_opencode(self, prompt: str) -> str:
        cmd = [
            str(self.command),
            "run",
            "--format",
            "json",
            "--model",
            self.model,
            prompt,
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stdout_lines: list[str] = []
        lock = threading.Lock()
        last_activity = time.monotonic()
        _ACTIVITY_TYPES = frozenset(("text", "reasoning", "tool_use", "step_start", "step_finish"))

        def _reader() -> None:
            nonlocal last_activity
            if proc.stdout is None:
                return
            for line in proc.stdout:
                with lock:
                    stdout_lines.append(line)
                    if line.strip():
                        try:
                            event = json.loads(line)
                            if event.get("type") in _ACTIVITY_TYPES:
                                last_activity = time.monotonic()
                        except json.JSONDecodeError:
                            pass

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        # Monitor progress
        while proc.poll() is None:
            elapsed = time.monotonic() - last_activity
            if elapsed > self.idle_timeout:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise RuntimeError(f"OpenCode idle for {self.idle_timeout:.0f}s")
            time.sleep(0.5)

        reader_thread.join(timeout=5)
        stdout = "".join(stdout_lines)

        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"OpenCode failed: {stderr.strip()}")

        return self._parse_output(stdout)

    @staticmethod
    def _parse_output(stdout: str) -> str:
        parts: list[str] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
                if event.get("type") == "text":
                    parts.append(event["part"]["text"])
            except (json.JSONDecodeError, KeyError):
                continue
        return "".join(parts)

    @staticmethod
    def _extract_files(output: str) -> list[str]:
        """Extract file paths from markdown code blocks."""
        pattern = re.compile(r"```\w*\n#\s*(.+?)\n", re.MULTILINE)
        return pattern.findall(output)
