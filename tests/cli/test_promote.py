"""Tests for optagent CLI promote command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.predict import run_predict_command
from optagent.cli.commands.promote import run_promote_command, cli_promote
from optagent.cli.main import parse_args, main


class TestCliPromoteCommand:
    """TDD for optagent promote CLI."""

    def _create_run_with_prediction(self, store_dir: Path) -> tuple[str, str, str]:
        """Helper: create run, plan, predict → return (run_id, plan_id, predicted_id)."""
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
        plan_id = plan_result["plans"][0]["plan_id"]
        predict_result = run_predict_command(
            run_id=run_id,
            plan_id=plan_id,
            predictor="default",
            max_outcomes=1,
            store_dir=str(store_dir),
        )
        predicted_id = predict_result["predictions"][0]["transition_id"]
        return run_id, plan_id, predicted_id

    def test_promote_creates_observed_transition_with_match(self):
        """promote should create an ObservedTransition linked to a prediction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id, predicted_id = self._create_run_with_prediction(store_dir)

            result = run_promote_command(
                run_id=run_id,
                predicted_transition_id=predicted_id,
                result_id="r_0001",
                status="completed",
                execution_plan_id=plan_id,
                metrics={},
                store_dir=str(store_dir),
            )
            assert result["transition"]["transition_kind"] == "observed"
            assert result["transition"]["matched_predicted_transition_id"] == predicted_id
            assert result["transition"]["action_result"]["result_id"] == "r_0001"

    def test_promote_appends_observed_state(self):
        """promote should append an observed state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id, predicted_id = self._create_run_with_prediction(store_dir)

            from optagent.storage.jsonl import JsonlRunStore
            store = JsonlRunStore(store_dir)
            before = set(store.load_run(run_id).trace_dag.nodes)

            run_promote_command(
                run_id=run_id,
                predicted_transition_id=predicted_id,
                result_id="r_0001",
                status="completed",
                execution_plan_id=plan_id,
                metrics={},
                store_dir=str(store_dir),
            )

            after = set(store.load_run(run_id).trace_dag.nodes)
            assert after != before

    def test_promote_unknown_run_id(self):
        """promote with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_promote_command(
                    run_id="nonexistent",
                    predicted_transition_id="t_pred_0001",
                    result_id="r_0001",
                    status="completed",
                    execution_plan_id=None,
                    metrics={},
                    store_dir=str(store_dir),
                )

    def test_promote_unknown_predicted_id(self):
        """promote with unknown predicted_transition_id should raise KeyError."""
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
                run_promote_command(
                    run_id=run_id,
                    predicted_transition_id="nonexistent",
                    result_id="r_0001",
                    status="completed",
                    execution_plan_id=None,
                    metrics={},
                    store_dir=str(store_dir),
                )

    def test_cli_parse_args_promote(self):
        """argparse should correctly parse promote subcommand."""
        args = parse_args([
            "promote", "--run", "my_run",
            "--predicted-transition-id", "t_pred_0001",
            "--execution-plan-id", "p_exec_0001",
            "--result-id", "r_0001",
        ])
        assert args.command == "promote"
        assert args.run == "my_run"
        assert args.predicted_transition_id == "t_pred_0001"
        assert args.result_id == "r_0001"
        assert args.status == "completed"

    def test_cli_parse_args_promote_with_options(self):
        """argparse should handle all promote options."""
        args = parse_args([
            "promote", "--run", "my_run",
            "--predicted-transition-id", "t_pred_0001",
            "--result-id", "r_0001",
            "--status", "failed",
            "--execution-plan-id", "p_exec_0001",
            "--metric", "speedup=1.15",
            "--store-dir", "/tmp/runs",
        ])
        assert args.status == "failed"
        assert args.execution_plan_id == "p_exec_0001"
        assert args.metric == ["speedup=1.15"]
        assert args.store_dir == "/tmp/runs"

    def test_main_promote_command(self, capsys):
        """main() should execute promote and print transition JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id, predicted_id = self._create_run_with_prediction(store_dir)

            exit_code = main([
                "promote", "--run", run_id,
                "--predicted-transition-id", predicted_id,
                "--result-id", "r_0001",
                "--execution-plan-id", plan_id,
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            transition = json.loads(captured.out)
            assert transition["transition_kind"] == "observed"
            assert transition["matched_predicted_transition_id"] == predicted_id

    def test_promote_returns_json_serializable(self):
        """run_promote_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, plan_id, predicted_id = self._create_run_with_prediction(store_dir)

            result = run_promote_command(
                run_id=run_id,
                predicted_transition_id=predicted_id,
                result_id="r_0001",
                status="completed",
                execution_plan_id=plan_id,
                metrics={},
                store_dir=str(store_dir),
            )
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert parsed["transition"]["action_result"]["status"] == "completed"
