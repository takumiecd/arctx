"""Tests for optagent CLI predict command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.predict import run_predict_command, cli_predict
from optagent.cli.main import parse_args, main


class TestCliPredictCommand:
    """TDD for optagent predict CLI."""

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

    def test_predict_creates_predicted_transitions(self):
        """predict should create PredictedTransitions for a plan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id = self._create_run_with_plan(store_dir)

            result = run_predict_command(
                run_id=run_id,
                plan_id=plan_id,
                predictor="default",
                max_outcomes=2,
                store_dir=str(store_dir),
            )
            assert len(result["predictions"]) == 2
            assert result["predictions"][0]["transition_kind"] == "predicted"
            assert result["predictions"][0]["parent_plan_id"] == plan_id

    def test_predict_saves_back_to_store(self):
        """predict should persist predictions to the run directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id = self._create_run_with_plan(store_dir)

            run_predict_command(
                run_id=run_id,
                plan_id=plan_id,
                predictor="default",
                max_outcomes=1,
                store_dir=str(store_dir),
            )

            from optagent.storage.jsonl import JsonlRunStore
            store = JsonlRunStore(store_dir)
            loaded = store.load_run(run_id)
            assert len(loaded.prediction_dag.transitions) == 1

    def test_predict_unknown_run_id(self):
        """predict with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_predict_command(
                    run_id="nonexistent",
                    plan_id="p_exec_0001",
                    predictor="default",
                    max_outcomes=1,
                    store_dir=str(store_dir),
                )

    def test_predict_unknown_plan_id(self):
        """predict with unknown plan_id should raise KeyError."""
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
                run_predict_command(
                    run_id=run_id,
                    plan_id="nonexistent",
                    predictor="default",
                    max_outcomes=1,
                    store_dir=str(store_dir),
                )

    def test_cli_parse_args_predict(self):
        """argparse should correctly parse predict subcommand."""
        args = parse_args(["predict", "p_exec_0001", "--run", "my_run"])
        assert args.command == "predict"
        assert args.run == "my_run"
        assert args.plan_id == "p_exec_0001"
        assert args.predictor == "default"
        assert args.max_outcomes == 1

    def test_cli_parse_args_predict_with_options(self):
        """argparse should handle all predict options."""
        args = parse_args([
            "predict", "p_exec_0001", "--run", "my_run",
            "--predictor", "custom",
            "--max-outcomes", "5",
            "--store-dir", "/tmp/runs",
        ])
        assert args.command == "predict"
        assert args.predictor == "custom"
        assert args.max_outcomes == 5
        assert args.store_dir == "/tmp/runs"

    def test_main_predict_command(self, capsys):
        """main() should execute predict and print predictions JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id = self._create_run_with_plan(store_dir)

            exit_code = main([
                "predict", plan_id, "--run", run_id,
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            predictions = json.loads(captured.out)
            assert len(predictions) == 1
            assert predictions[0]["transition_kind"] == "predicted"

    def test_predict_returns_json_serializable(self):
        """run_predict_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id = self._create_run_with_plan(store_dir)

            result = run_predict_command(
                run_id=run_id,
                plan_id=plan_id,
                predictor="default",
                max_outcomes=3,
                store_dir=str(store_dir),
            )
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert len(parsed["predictions"]) == 3
