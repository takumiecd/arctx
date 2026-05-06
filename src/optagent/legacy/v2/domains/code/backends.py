"""Adapter: wrap v1 OpenCodeBackend as v2 LLMBackend."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from optagent.legacy.v2.domains.code.proposer import LLMBackend


class OpenCodeBackendAdapter:
    """Adapter that wraps OpenCode CLI directly to satisfy v2 LLMBackend protocol."""

    def __init__(self, command: str = "/home/ware10sai/.opencode/bin/opencode", model: str = "opencode-go/kimi-k2.6", timeout: float = 180.0):
        self.command = Path(command)
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str, n: int, temperature: float) -> list[str]:
        """Call OpenCode CLI to generate optimization diffs.

        Uses streaming with idle timeout (like v1 OpenCodeBackend)
        to avoid killing the process during long reasoning/thinking.
        """
        cmd = [
            str(self.command),
            "run",
            "--format", "json",
            "--model", self.model,
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
        import threading
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

        # Monitor: abort only if idle for too long (not total wall time)
        while proc.poll() is None:
            elapsed = time.monotonic() - last_activity
            if elapsed > self.timeout:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise RuntimeError(f"OpenCode idle for {self.timeout:.0f}s")
            time.sleep(0.5)

        reader_thread.join(timeout=5)
        stdout = "".join(stdout_lines)

        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"OpenCode failed: {stderr.strip()}")

        # Parse JSONL output
        responses = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if event.get("type") == "text":
                    responses.append(event["part"]["text"])
            except (json.JSONDecodeError, KeyError):
                continue

        if not responses:
            return []
        full_response = "".join(responses)
        return [full_response]
