"""Tests for v2 domains/code/ executor."""

import unittest
import tempfile
from pathlib import Path

from optagent.legacy.v2.domains.code.executor import CodeExecutor
from optagent.legacy.v2.domains.code.state import CodeState, CodeArtifact
from optagent.legacy.v2.domains.code.action import EditCode, RunTests, RunBenchmark


class TestCodeExecutor(unittest.TestCase):
    def setUp(self):
        self.work_dir = Path(tempfile.mkdtemp(prefix="optagent_test_"))
        self.executor = CodeExecutor(work_dir=self.work_dir)

    def test_apply_diff_success(self):
        """Diff application produces expected patched content."""
        source = self.work_dir / "source.py"
        source.write_text("def hello():\n    return 'hello'\n")

        diff = """\
--- a/source.py
+++ b/source.py
@@ -1,2 +1,2 @@
 def hello():
-    return 'hello'
+    return 'world'
"""

        state = CodeState(
            requirement={},
            code=CodeArtifact(
                artifact_id="test",
                source_path=source,
                content=source.read_text(),
            ),
        )
        action = EditCode(diff=diff, target_path=source)
        result = self.executor.apply_diff(state, action)

        self.assertTrue(result["success"])
        self.assertIn("return 'world'", result["patched_content"])

    def test_apply_diff_failure(self):
        """Invalid unified diff returns success=False."""
        source = self.work_dir / "source.py"
        source.write_text("def hello():\n    return 'hello'\n")

        state = CodeState(
            requirement={},
            code=CodeArtifact(
                artifact_id="test",
                source_path=source,
                content=source.read_text(),
            ),
        )
        # Invalid unified diff (malformed hunk)
        action = EditCode(diff="--- a/source.py\n+++ b/source.py\n@@ -1 +1 @@\n-garbage\n", target_path=source)
        result = self.executor.apply_diff(state, action)

        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_run_tests_success(self):
        """Running tests on passing test file."""
        test_file = self.work_dir / "test_sample.py"
        test_file.write_text("""\
def test_ok():
    assert True
""")

        source = self.work_dir / "module.py"
        source.write_text("")

        state = CodeState(
            requirement={},
            code=CodeArtifact(
                artifact_id="test",
                source_path=source,
                content="",
            ),
        )
        action = RunTests(test_command="pytest -q --tb=no", target_path=self.work_dir)
        result = self.executor.run_tests(state, action)

        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["test_count"], 1)

    def test_run_tests_failure(self):
        """Running tests on failing test file."""
        test_file = self.work_dir / "test_fail.py"
        test_file.write_text("""\
def test_fail():
    assert False
""")

        source = self.work_dir / "module.py"
        source.write_text("")

        state = CodeState(
            requirement={},
            code=CodeArtifact(
                artifact_id="test",
                source_path=source,
                content="",
            ),
        )
        action = RunTests(test_command="pytest -q --tb=no", target_path=self.work_dir)
        result = self.executor.run_tests(state, action)

        self.assertFalse(result["passed"])
        self.assertGreaterEqual(len(result["failed"]), 0)

    def test_run_benchmark(self):
        """Benchmark executes without error."""
        bench_script = self.work_dir / "bench.py"
        bench_script.write_text("sum(range(100))\n")

        state = CodeState(
            requirement={},
            code=CodeArtifact(
                artifact_id="test",
                source_path=bench_script,
                content=bench_script.read_text(),
            ),
        )
        action = RunBenchmark(
            benchmark_command=f"python3 -m timeit -n 1 -r 1 'exec(open(\"{bench_script}\").read())'",
        )
        result = self.executor.run_benchmark(state, action)

        self.assertNotIn("error", result)
        self.assertIn("latency_ms", result)


class TestParseTimeit(unittest.TestCase):
    def test_sec(self):
        self.assertAlmostEqual(
            CodeExecutor._parse_timeit_output("best of 5: 1.23 sec per loop"),
            1230.0,
        )

    def test_msec(self):
        self.assertAlmostEqual(
            CodeExecutor._parse_timeit_output("best of 5: 4.56 msec per loop"),
            4.56,
        )

    def test_usec(self):
        self.assertAlmostEqual(
            CodeExecutor._parse_timeit_output("best of 5: 789 usec per loop"),
            0.789,
        )

    def test_invalid(self):
        self.assertEqual(
            CodeExecutor._parse_timeit_output("no time here"),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
