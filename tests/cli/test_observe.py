"""Tests for optagent CLI observe command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.observe import run_observe_command, cli_observe
from optagent.cli.main import parse_args, main


class TestCliObserveCommand:
    """TDD for optagent observe CLI."""

    def _create_run_with_plan(self, store_dir: Path) -> tuple[str, str]:
        """Helper: create a run, add a plan, return (run_id, plan_id)."""
        result = run_init_command(
            requirement_id="req_test",
            target_type="code",
            target_id="module_a",
            run_id=None,
            store_dir=str(store_dir),
        )
        run_id = result["run_id"]
        plan_result = run_plan_command(
            run_id=run_id,
            planner="default",
            max_plans=1,
            store_dir=str(store_dir),
            from_state_id="s_obs_0000",
        )
        return run_id, plan_result["plans"][0]["plan_id"]

    def test_observe_creates_observed_transition(self):
        """observe should create an ObservedTransition for a plan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id = self._create_run_with_plan(store_dir)

            result = run_observe_command(
                run_id=run_id,
                plan_id=plan_id,
                result_id="r_0001",
                status="completed",
                artifacts=["patch.diff"],
                raw_outputs=["bench.txt"],
                logs=["build.log"],
                metrics={"speedup": 1.15},
                errors=[],
                store_dir=str(store_dir),
            )
            assert result["transition"]["transition_kind"] == "observed"
            assert result["transition"]["execution_plan_id"] == plan_id
            assert result["transition"]["action_result"]["result_id"] == "r_0001"
            assert result["transition"]["action_result"]["status"] == "completed"

    def test_observe_appends_new_state(self):
        """observe should append a new observed state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id = self._create_run_with_plan(store_dir)

            from optagent.storage.jsonl import JsonlRunStore
            store = JsonlRunStore(store_dir)
            before = store.load_run(run_id)
            before_states = set(before.trace_dag.nodes)

            run_observe_command(
                run_id=run_id,
                plan_id=plan_id,
                result_id="r_0001",
                status="completed",
                artifacts=[],
                raw_outputs=[],
                logs=[],
                metrics={},
                errors=[],
                store_dir=str(store_dir),
            )

            after = store.load_run(run_id)
            assert set(after.trace_dag.nodes) != before_states

    def test_observe_saves_metrics(self):
        """--metric should populate ActionResult.metrics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id = self._create_run_with_plan(store_dir)

            result = run_observe_command(
                run_id=run_id,
                plan_id=plan_id,
                result_id="r_0001",
                status="completed",
                artifacts=[],
                raw_outputs=[],
                logs=[],
                metrics={"speedup": 1.15, "latency_ms": 12.3},
                errors=[],
                store_dir=str(store_dir),
            )
            metrics = result["transition"]["action_result"]["metrics"]
            assert metrics["speedup"] == 1.15
            assert metrics["latency_ms"] == 12.3

    def test_observe_unknown_run_id(self):
        """observe with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_observe_command(
                    run_id="nonexistent",
                    plan_id="p_exec_0001",
                    result_id="r_0001",
                    status="completed",
                    artifacts=[],
                    raw_outputs=[],
                    logs=[],
                    metrics={},
                    errors=[],
                    store_dir=str(store_dir),
                )

    def test_observe_unknown_plan_id(self):
        """observe with unknown plan_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            result = run_init_command(
                requirement_id="req_test",
                target_type="code",
                target_id="module_a",
                run_id=None,
                store_dir=str(store_dir),
            )
            run_id = result["run_id"]
            with pytest.raises(KeyError):
                run_observe_command(
                    run_id=run_id,
                    plan_id="nonexistent",
                    result_id="r_0001",
                    status="completed",
                    artifacts=[],
                    raw_outputs=[],
                    logs=[],
                    metrics={},
                    errors=[],
                    store_dir=str(store_dir),
                )

    def test_cli_parse_args_observe(self):
        """argparse should correctly parse observe subcommand."""
        args = parse_args([
            "observe", "--plan", "p_exec_0001", "--run", "my_run", "--result-id", "r_0001"
        ])
        assert args.command == "observe"
        assert args.run == "my_run"
        assert args.plan_id == "p_exec_0001"
        assert args.result_id == "r_0001"
        assert args.status == "completed"

    def test_cli_parse_args_observe_with_options(self):
        """argparse should handle all observe options."""
        args = parse_args([
            "observe", "--plan", "p_exec_0001", "--run", "my_run",
            "--result-id", "r_0001",
            "--status", "failed",
            "--artifact", "patch.diff",
            "--raw-output", "bench.txt",
            "--log", "build.log",
            "--metric", "speedup=1.15",
            "--error", "timeout",
            "--store-dir", "/tmp/runs",
        ])
        assert args.command == "observe"
        assert args.status == "failed"
        assert args.artifact == ["patch.diff"]
        assert args.raw_output == ["bench.txt"]
        assert args.log == ["build.log"]
        assert args.metric == ["speedup=1.15"]
        assert args.error == ["timeout"]
        assert args.store_dir == "/tmp/runs"

    def test_main_observe_command(self, capsys):
        """main() should execute observe and print transition JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id = self._create_run_with_plan(store_dir)

            exit_code = main([
                "observe", "--plan", plan_id, "--run", run_id,
                "--result-id", "r_0001",
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            transition = json.loads(captured.out)
            assert transition["transition_kind"] == "observed"
            assert transition["action_result"]["result_id"] == "r_0001"

    def test_observe_returns_json_serializable(self):
        """run_observe_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id = self._create_run_with_plan(store_dir)

            result = run_observe_command(
                run_id=run_id,
                plan_id=plan_id,
                result_id="r_0001",
                status="completed",
                artifacts=["a.patch"],
                raw_outputs=["out.txt"],
                logs=["log.txt"],
                metrics={"speedup": 1.2},
                errors=[],
                store_dir=str(store_dir),
            )
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert parsed["transition"]["action_result"]["status"] == "completed"
