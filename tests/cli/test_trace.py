"""Tests for optagent CLI trace command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.trace import run_trace_command, cli_trace
from optagent.cli.main import parse_args, main


class TestCliTraceCommand:
    """TDD for optagent trace CLI."""

    def _create_run_with_observations(self, store_dir: Path) -> str:
        """Helper: create run with 2 observed transitions."""
        result = run_init_command(
            requirement_id="req_test",
            target_type="code",
            target_id="module_a",
            run_id=None,
            store_dir=str(store_dir),
        )
        run_id = result["run_id"]

        # First plan + observe
        plan1 = run_plan_command(
            run_id=run_id,
            planner="default",
            max_plans=1,
            store_dir=str(store_dir),
            from_state_id="s_obs_0000",
        )
        first = run_observe_command(
            run_id=run_id, plan_id=plan1["plans"][0]["plan_id"],
            result_id="r_0001", status="completed",
            artifacts=[], raw_outputs=[], logs=[], metrics={}, errors=[],
            store_dir=str(store_dir),
        )

        # Second plan + observe
        plan2 = run_plan_command(
            run_id=run_id,
            planner="default",
            max_plans=1,
            store_dir=str(store_dir),
            from_state_id=first["transition"]["to_observed_state_id"],
        )
        run_observe_command(
            run_id=run_id, plan_id=plan2["plans"][0]["plan_id"],
            result_id="r_0002", status="completed",
            artifacts=[], raw_outputs=[], logs=[], metrics={}, errors=[],
            store_dir=str(store_dir),
        )

        return run_id

    def test_trace_returns_history(self):
        """trace should return observed transition history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observations(store_dir)

            result = run_trace_command(
                run_id=run_id,
                from_state_id="s_obs_0002",
                depth=3,
                store_dir=str(store_dir),
            )
            assert len(result["history"]["observed_transition_ids"]) == 2
            assert len(result["history"]["action_result_ids"]) == 2

    def test_trace_respects_depth(self):
        """--depth should limit the number of transitions returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observations(store_dir)

            result = run_trace_command(
                run_id=run_id,
                from_state_id="s_obs_0002",
                depth=1,
                store_dir=str(store_dir),
            )
            assert len(result["history"]["observed_transition_ids"]) == 1

    def test_trace_unknown_run_id(self):
        """trace with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_trace_command(
                    run_id="nonexistent",
                    from_state_id="s_obs_0000",
                    depth=3,
                    store_dir=str(store_dir),
                )

    def test_trace_empty_run(self):
        """trace on a run with no observations should return empty history."""
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

            trace_result = run_trace_command(
                run_id=run_id,
                from_state_id="s_obs_0000",
                depth=3,
                store_dir=str(store_dir),
            )
            assert trace_result["history"]["observed_transition_ids"] == []

    def test_cli_parse_args_trace(self):
        """argparse should correctly parse trace subcommand."""
        args = parse_args(["trace", "--run", "my_run", "--from-state", "s_obs_0001"])
        assert args.command == "trace"
        assert args.run == "my_run"
        assert args.depth is None

    def test_cli_parse_args_trace_with_options(self):
        """argparse should handle all trace options."""
        args = parse_args([
            "trace", "--run", "my_run",
            "--from-state", "s_obs_0001",
            "--depth", "5",
            "--store-dir", "/tmp/runs",
        ])
        assert args.depth == 5
        assert args.store_dir == "/tmp/runs"

    def test_main_trace_command(self, capsys):
        """main() should execute trace and print history JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observations(store_dir)

            exit_code = main([
                "trace", "--run", run_id,
                "--from-state", "s_obs_0002",
                "--depth", "3",
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            history = json.loads(captured.out)
            assert len(history["observed_transition_ids"]) == 2

    def test_trace_returns_json_serializable(self):
        """run_trace_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observations(store_dir)

            result = run_trace_command(
                run_id=run_id,
                from_state_id="s_obs_0002",
                depth=3,
                store_dir=str(store_dir),
            )
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert len(parsed["history"]["observed_transition_ids"]) == 2
