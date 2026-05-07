"""Tests for optagent CLI refresh command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.refresh import run_refresh_command, cli_refresh
from optagent.cli.main import parse_args, main


class TestCliRefreshCommand:
    """TDD for optagent refresh CLI."""

    def _create_run_with_observation(self, store_dir: Path) -> str:
        """Helper: create run, plan, observe → return run_id."""
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
        )
        run_observe_command(
            run_id=run_id,
            plan_id=plan_result["plans"][0]["plan_id"],
            result_id="r_0001",
            status="completed",
            artifacts=[], raw_outputs=[], logs=[], metrics={}, errors=[],
            store_dir=str(store_dir),
        )
        return run_id

    def test_refresh_reanchors_prediction_dag(self):
        """refresh should re-anchor PredictionDAG to current observed state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            from optagent.storage.jsonl import JsonlRunStore
            store = JsonlRunStore(store_dir)
            before = store.load_run(run_id)
            old_anchor = before.prediction_dag.anchor_observed_state_id
            old_root = before.prediction_dag.root_predicted_state_id

            result = run_refresh_command(
                run_id=run_id,
                store_dir=str(store_dir),
            )
            assert result["prediction_dag"]["anchor_observed_state_id"] != old_anchor
            assert result["prediction_dag"]["root_predicted_state_id"] != old_root
            assert result["prediction_dag"]["anchor_observed_state_id"] == before.current_observed_state_id

    def test_refresh_unknown_run_id(self):
        """refresh with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_refresh_command(
                    run_id="nonexistent",
                    store_dir=str(store_dir),
                )

    def test_cli_parse_args_refresh(self):
        """argparse should correctly parse refresh subcommand."""
        args = parse_args(["refresh", "--run", "my_run"])
        assert args.command == "refresh"
        assert args.run == "my_run"

    def test_cli_parse_args_refresh_with_store_dir(self):
        """argparse should handle --store-dir for refresh."""
        args = parse_args([
            "refresh", "--run", "my_run",
            "--store-dir", "/tmp/runs",
        ])
        assert args.store_dir == "/tmp/runs"

    def test_main_refresh_command(self, capsys):
        """main() should execute refresh and print prediction dag JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            exit_code = main([
                "refresh", "--run", run_id,
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            dag = json.loads(captured.out)
            assert "dag_id" in dag
            assert "anchor_observed_state_id" in dag

    def test_refresh_returns_json_serializable(self):
        """run_refresh_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            result = run_refresh_command(
                run_id=run_id,
                store_dir=str(store_dir),
            )
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert parsed["prediction_dag"]["dag_id"].startswith("prediction_dag_")
