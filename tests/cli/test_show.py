"""Tests for optagent CLI show command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.show import run_show_command, cli_show
from optagent.cli.main import parse_args, main


class TestCliShowCommand:
    """TDD for optagent show CLI."""

    def _create_run_with_history(self, store_dir: Path) -> str:
        """Helper: create run with plan and observation."""
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
        run_observe_command(
            run_id=run_id,
            plan_id=plan_result["plans"][0]["plan_id"],
            result_id="r_0001",
            status="completed",
            artifacts=["patch.diff"],
            raw_outputs=["bench.txt"],
            logs=["build.log"],
            metrics={"speedup": 1.15},
            errors=[],
            store_dir=str(store_dir),
        )
        return run_id

    def test_show_run_summary(self):
        """show should return run summary by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_history(store_dir)

            result = run_show_command(
                run_id=run_id,
                state_id=None,
                plan_id=None,
                transition_id=None,
                store_dir=str(store_dir),
            )
            assert result["run_id"] == run_id
            assert result["requirement_id"] == "req_test"
            assert result["root_observed_state_id"] == "s_obs_0000"
            assert "trace_dag" in result
            assert "prediction_dag" in result

    def test_show_state(self):
        """show --state should return a specific state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_history(store_dir)

            result = run_show_command(
                run_id=run_id,
                state_id="s_obs_0000",
                plan_id=None,
                transition_id=None,
                store_dir=str(store_dir),
            )
            assert result["state"]["state_id"] == "s_obs_0000"
            assert result["state"]["state_kind"] == "observed"

    def test_show_plan(self):
        """show --plan should return a specific plan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_history(store_dir)

            from optagent.storage.jsonl import JsonlRunStore
            store = JsonlRunStore(store_dir)
            loaded = store.load_run(run_id)
            plan_id = list(loaded.trace_dag.execution_plans.keys())[0]

            result = run_show_command(
                run_id=run_id,
                state_id=None,
                plan_id=plan_id,
                transition_id=None,
                store_dir=str(store_dir),
            )
            assert result["plan"]["plan_id"] == plan_id
            assert result["plan"]["plan_kind"] == "execution"

    def test_show_transition(self):
        """show --transition should return a specific transition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_history(store_dir)

            from optagent.storage.jsonl import JsonlRunStore
            store = JsonlRunStore(store_dir)
            loaded = store.load_run(run_id)
            transition_id = list(loaded.trace_dag.transitions.keys())[0]

            result = run_show_command(
                run_id=run_id,
                state_id=None,
                plan_id=None,
                transition_id=transition_id,
                store_dir=str(store_dir),
            )
            assert result["transition"]["transition_id"] == transition_id
            assert result["transition"]["transition_kind"] == "observed"

    def test_show_unknown_run_id(self):
        """show with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_show_command(
                    run_id="nonexistent",
                    state_id=None,
                    plan_id=None,
                    transition_id=None,
                    store_dir=str(store_dir),
                )

    def test_show_unknown_state_id(self):
        """show with unknown state_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_history(store_dir)
            with pytest.raises(KeyError):
                run_show_command(
                    run_id=run_id,
                    state_id="nonexistent",
                    plan_id=None,
                    transition_id=None,
                    store_dir=str(store_dir),
                )

    def test_cli_parse_args_show(self):
        """argparse should correctly parse show subcommand."""
        args = parse_args(["show", "--run", "my_run"])
        assert args.command == "show"
        assert args.run == "my_run"
        assert args.state_id is None
        assert args.plan_id is None
        assert args.transition_id is None

    def test_cli_parse_args_show_with_options(self):
        """argparse should handle all show options."""
        args = parse_args([
            "show", "--run", "my_run",
            "--state", "s_obs_0000",
            "--store-dir", "/tmp/runs",
        ])
        assert args.state_id == "s_obs_0000"
        assert args.store_dir == "/tmp/runs"

    def test_main_show_command(self, capsys):
        """main() should execute show and print JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_history(store_dir)

            exit_code = main([
                "show", "--run", run_id,
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            result = json.loads(captured.out)
            assert result["run_id"] == run_id

    def test_show_returns_json_serializable(self):
        """run_show_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_history(store_dir)

            result = run_show_command(
                run_id=run_id,
                state_id=None,
                plan_id=None,
                transition_id=None,
                store_dir=str(store_dir),
            )
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert parsed["run_id"] == run_id
