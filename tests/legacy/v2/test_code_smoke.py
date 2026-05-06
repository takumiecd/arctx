"""Integration test: real backend smoke test for CodeOptimizer.

This test creates a real Python file and attempts optimization.
It is skipped if no backend is available.
"""

import unittest
import tempfile
from pathlib import Path

from optagent.legacy.v2.domains.code.optimizer import CodeOptimizer
from optagent.legacy.v2.domains.code.backends import OpenCodeBackendAdapter
from optagent.legacy.v1.backends.opencode import OpenCodeBackend


class TestCodeOptimizerSmoke(unittest.TestCase):
    def setUp(self):
        self.work_dir = Path(tempfile.mkdtemp(prefix="optagent_smoke_"))
        self.source = self.work_dir / "slow_sum.py"
        self.source.write_text("""\
def slow_sum(n):
    \"\"\"Sum from 0 to n-1 using a loop.\"\"\"
    s = 0
    for i in range(n):
        s += i
    return s


def test_slow_sum():
    assert slow_sum(10) == 45
    assert slow_sum(100) == 4950
""")

    def test_with_opencode_backend(self):
        """Run CodeOptimizer with OpenCodeBackend."""
        try:
            backend = OpenCodeBackend()
            if not backend.is_available():
                self.skipTest("OpenCode backend not available")
        except Exception as e:
            self.skipTest(f"OpenCode backend unavailable: {e}")

        adapter = OpenCodeBackendAdapter(backend)
        opt = CodeOptimizer(
            source_path=self.source,
            backend=adapter,
            work_dir=self.work_dir,
        )

        result = opt.optimize(objective="minimize latency", max_rounds=1)
        self.assertIsNotNone(result)
        print("Optimized code:")
        print(result.code.content)

    def test_mock_backend(self):
        """Run CodeOptimizer without real backend."""
        opt = CodeOptimizer(
            source_path=self.source,
            backend=None,
            work_dir=self.work_dir,
        )
        result = opt.optimize(objective="minimize latency", max_rounds=1)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
