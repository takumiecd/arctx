"""§11.3 CodeExecutor — diff apply, test run, benchmark.

Corresponds to PLANNING_AND_RL.md §11.3.

Handles the concrete execution of code actions:
1. Apply diff to source files
2. Run tests
3. Run benchmarks
"""

from __future__ import annotations

import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

from optagent.legacy.v2.domains.code.action import EditCode, RunTests, RunBenchmark
from optagent.legacy.v2.domains.code.state import CodeState


class CodeExecutor:
    """Execute code actions in isolated environment."""

    def __init__(self, work_dir: Optional[Path] = None):
        self.work_dir = work_dir or Path(tempfile.mkdtemp(prefix="optagent_code_"))
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def apply_diff(self, state: CodeState, action: EditCode) -> Dict[str, Any]:
        """Apply diff to source file.

        If the diff looks like a complete file (not a unified diff), replaces the entire file.
        Otherwise, uses the patch command.

        Returns:
            dict with keys: success (bool), patched_content (str), error (str)
        """
        target = action.target_path or state.code.source_path
        if not target.exists():
            return {"success": False, "error": f"Target not found: {target}"}

        diff = action.diff

        # Check if diff is a complete file replacement (no ---/+++ header)
        if not diff.lstrip().startswith("---"):
            # Treat as complete file replacement
            return {"success": True, "patched_content": diff.strip()}

        # Unified diff: use patch command
        cleaned_diff = "\n".join(line.rstrip() for line in diff.splitlines())
        # Ensure trailing newline for patch command
        if not cleaned_diff.endswith("\n"):
            cleaned_diff += "\n"
        diff_hash = hash(cleaned_diff) & 0xFFFFFFFF
        diff_file = self.work_dir / f"{diff_hash:08x}.diff"
        diff_file.write_text(cleaned_diff)

        # Copy original to work dir (use a different name to avoid collision), apply patch there
        work_copy = self.work_dir / f"copy_{target.name}"
        shutil.copy2(target, work_copy)

        try:
            result = subprocess.run(
                ["patch", "-u", str(work_copy), "-i", str(diff_file)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                patched = work_copy.read_text()
                return {"success": True, "patched_content": patched}
            else:
                return {"success": False, "error": result.stderr}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_tests(self, state: CodeState, action: RunTests) -> Dict[str, Any]:
        """Run test suite.

        Returns:
            dict with keys: passed (bool), test_count (int), failed (list), output (str)
        """
        target_dir = action.target_path or state.code.source_path.parent
        try:
            result = subprocess.run(
                action.test_command.split(),
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            passed = result.returncode == 0
            output = result.stdout + result.stderr

            # Parse pytest output: "N passed, M failed" or "N passed in ..."
            import re
            test_count = 0
            failed_tests = []

            # Count passed/failed from pytest summary
            passed_match = re.search(r'(\d+) passed', output)
            failed_match = re.search(r'(\d+) failed', output)
            if passed_match:
                test_count += int(passed_match.group(1))
            if failed_match:
                failed_count = int(failed_match.group(1))
                test_count += failed_count
                # Extract failed test names
                for line in output.split('\n'):
                    if 'FAILED' in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == 'FAILED' and i + 1 < len(parts):
                                failed_tests.append(parts[i + 1])

            return {
                "passed": passed,
                "test_count": test_count,
                "failed": failed_tests,
                "output": output,
            }
        except Exception as e:
            return {"passed": False, "error": str(e)}

    def run_benchmark(self, state: CodeState, action: RunBenchmark) -> Dict[str, Any]:
        """Run benchmark and collect metrics.

        Returns:
            dict with keys: latency_ms (float), memory_mb (float), iterations (int)
        """
        target_dir = state.code.source_path.parent
        try:
            result = subprocess.run(
                action.benchmark_command.split(),
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            latency_ms = self._parse_timeit_output(result.stdout)
            return {
                "latency_ms": latency_ms,
                "memory_mb": 0.0,  # TODO: measure memory
                "iterations": action.iterations,
                "raw_output": result.stdout,
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _parse_timeit_output(output: str) -> float:
        """Parse timeit output to latency in milliseconds.

        Supports formats:
        - 'best of 5: 1.23 msec per loop' (standard timeit)
        - '1.23 msec per loop' (custom script)
        """
        import re
        # Try standard timeit format first
        match = re.search(r'best of \d+: ([\d.]+)\s+(sec|msec|usec|nsec) per loop', output)
        if not match:
            # Fallback to simple format
            match = re.search(r'([\d.]+)\s+(sec|msec|usec|nsec) per loop', output)
        if not match:
            return 0.0
        value = float(match.group(1))
        unit = match.group(2)
        conversions = {
            "sec": 1000.0,
            "msec": 1.0,
            "usec": 0.001,
            "nsec": 0.000001,
        }
        return value * conversions.get(unit, 1.0)
