"""Tests for optagent CLI plan command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command, cli_plan
from optagent.cli.main import parse_args, main
from optagent.storage.jsonl import JsonlRunStore


class TestCliPlanCommand:
    """TDD for optagent plan CLI."""

    def _create_run(self, store_dir: Path, run_id: str = "test_run") -> str:
        """Helper: create a run and return its run_id."""
        result = run_init_command(
            requirement_id="req_test",
            target_type="code",
            target_id="module_a",
            run_id=run_id,
            store_dir=str(store_dir),
        )
        return result["run_id"]

    def test_plan_creates_execution_plan(self):
        """plan should create an ExecutionPlan from an explicit observed state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            result = run_plan_command(
                run_id=run_id,
                planner="default",
                max_plans=1,
                store_dir=str(store_dir),
                from_state_id="s_obs_0000",
            )
            assert len(result["plans"]) == 1
            assert result["plans"][0]["plan_kind"] == "execution"
            assert result["plans"][0]["from_observed_state_id"] == "s_obs_0000"

    def test_plan_saves_back_to_store(self):
        """plan should persist the created plans to the run directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            run_plan_command(
                run_id=run_id,
                planner="default",
                max_plans=1,
                store_dir=str(store_dir),
                from_state_id="s_obs_0000",
            )

            store = JsonlRunStore(store_dir)
            loaded = store.load_run(run_id)
            assert len(loaded.trace_dag.execution_plans) == 1

    def test_plan_multiple_plans(self):
        """--max-plans should control the number of plans created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            result = run_plan_command(
                run_id=run_id,
                planner="default",
                max_plans=3,
                store_dir=str(store_dir),
                from_state_id="s_obs_0000",
            )
            assert len(result["plans"]) == 3
            plan_ids = {p["plan_id"] for p in result["plans"]}
            assert len(plan_ids) == 3  # unique ids

    def test_plan_planner_metadata(self):
        """planner name should be recorded in plan metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            result = run_plan_command(
                run_id=run_id,
                planner="custom_planner",
                max_plans=1,
                store_dir=str(store_dir),
                from_state_id="s_obs_0000",
            )
            assert result["plans"][0]["metadata"]["planner"] == "custom_planner"

    def test_plan_unknown_run_id(self):
        """plan with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_plan_command(
                    run_id="nonexistent",
                    planner="default",
                    max_plans=1,
                    store_dir=str(store_dir),
                    from_state_id="s_obs_0000",
                )

    def test_cli_parse_args_plan(self):
        """argparse should correctly parse plan subcommand."""
        args = parse_args(["plan", "--run", "my_run", "--from-state", "s_obs_0000"])
        assert args.command == "plan"
        assert args.run == "my_run"
        assert args.planner == "default"
        assert args.max_plans == 1

    def test_cli_parse_args_plan_with_options(self):
        """argparse should handle all plan options."""
        args = parse_args([
            "plan", "--run", "my_run", "--from-state", "s_obs_0000",
            "--planner", "custom",
            "--max-plans", "5",
            "--store-dir", "/tmp/runs",
        ])
        assert args.command == "plan"
        assert args.run == "my_run"
        assert args.planner == "custom"
        assert args.max_plans == 5
        assert args.store_dir == "/tmp/runs"

    def test_main_plan_command(self, capsys):
        """main() should execute plan and print plans JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            exit_code = main([
                "plan", "--run", run_id,
                "--from-state", "s_obs_0000",
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            plans = json.loads(captured.out)
            assert len(plans) == 1
            assert plans[0]["plan_kind"] == "execution"

    def test_plan_returns_json_serializable(self):
        """run_plan_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            result = run_plan_command(
                run_id=run_id,
                planner="default",
                max_plans=2,
                store_dir=str(store_dir),
                from_state_id="s_obs_0000",
            )
            # Should not raise
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert len(parsed["plans"]) == 2

    def test_plan_with_action_type(self):
        """--action-type should set the plan's action_type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            result = run_plan_command(
                run_id=run_id,
                planner="default",
                max_plans=1,
                store_dir=str(store_dir),
                from_state_id="s_obs_0000",
                action_type="edit",
            )
            assert result["plans"][0]["action_type"] == "edit"

    def test_plan_with_intent(self):
        """--intent should set the plan's intent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            result = run_plan_command(
                run_id=run_id,
                planner="default",
                max_plans=1,
                store_dir=str(store_dir),
                from_state_id="s_obs_0000",
                intent="vectorize inner loop",
            )
            assert result["plans"][0]["intent"] == "vectorize inner loop"

    def test_plan_with_inputs(self):
        """--input should populate the plan's inputs dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            result = run_plan_command(
                run_id=run_id,
                planner="default",
                max_plans=1,
                store_dir=str(store_dir),
                from_state_id="s_obs_0000",
                inputs={"file": "src/kernel.py", "line_start": "42"},
            )
            assert result["plans"][0]["inputs"]["file"] == "src/kernel.py"
            assert result["plans"][0]["inputs"]["line_start"] == "42"

    def test_cli_parse_args_plan_with_content_options(self):
        """argparse should handle action-type, intent, and input."""
        args = parse_args([
            "plan", "--run", "my_run", "--from-state", "s_obs_0000",
            "--action-type", "edit",
            "--intent", "optimize loop",
            "--input", "file=main.py",
            "--input", "strategy=unroll",
        ])
        assert args.action_type == "edit"
        assert args.intent == "optimize loop"
        assert args.input == ["file=main.py", "strategy=unroll"]

    def test_plan_explicit_from_state(self):
        """--from-state should let plan target an observed state explicitly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            result = run_plan_command(
                run_id=run_id,
                planner="default",
                max_plans=1,
                store_dir=str(store_dir),
                from_state_id="s_obs_0000",
            )
            assert result["plans"][0]["from_observed_state_id"] == "s_obs_0000"

    def test_plan_rejects_predicted_state(self):
        """plan should refuse a predicted from_state_id (use 'extend' instead)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run(store_dir)

            with pytest.raises(KeyError, match="unknown observed state"):
                run_plan_command(
                    run_id=run_id,
                    planner="default",
                    max_plans=1,
                    store_dir=str(store_dir),
                    from_state_id="s_pred_0000",
                )
