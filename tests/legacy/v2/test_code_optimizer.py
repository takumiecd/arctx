"""Integration test for CodeOptimizer end-to-end flow."""

import unittest
import tempfile
from pathlib import Path

from optagent.legacy.v2.domains.code.optimizer import CodeOptimizer


class MockLLMBackend:
    """Mock backend that returns canned responses."""

    def __init__(self, responses: list[str] = None):
        self.responses = responses or []

    def complete(self, prompt: str, n: int, temperature: float) -> list[str]:
        return self.responses[:n]


class TestCodeOptimizer(unittest.TestCase):
    def setUp(self):
        self.work_dir = Path(tempfile.mkdtemp(prefix="optagent_opt_test_"))
        self.source = self.work_dir / "slow_loop.py"
        self.source.write_text("""\
def sum_loop(n):
    s = 0
    for i in range(n):
        s += i
    return s
""")

    def test_optimize_runs_without_error(self):
        """CodeOptimizer runs without crashing."""
        backend = MockLLMBackend([
            "--- a/slow_loop.py\n+++ b/slow_loop.py\n@@ -1,4 +1,2 @@\n def sum_loop(n):\n-    s = 0\n-    for i in range(n):\n-        s += i\n-    return s\n+    return sum(range(n))\n"
        ])
        opt = CodeOptimizer(
            source_path=self.source,
            backend=backend,
            work_dir=self.work_dir,
        )
        result = opt.optimize(objective="minimize latency", max_rounds=2)
        self.assertIsNotNone(result)
        self.assertEqual(result.code.source_path, self.source)

    def test_optimize_with_no_backend(self):
        """CodeOptimizer works without backend (mock mode)."""
        opt = CodeOptimizer(
            source_path=self.source,
            backend=None,
            work_dir=self.work_dir,
        )
        result = opt.optimize(objective="minimize latency", max_rounds=1)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
