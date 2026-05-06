"""Tests for optagent CLI state command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.state import run_state_command, cli_state
from optagent.cli.main import parse_args, main


class TestCliStateCommand:
    """TDD for optagent state CLI."""

    def _create_run_with_observation(self, store_dir: Path) -> tuple[str, str]:
        """Helper: create run with plan and observation → return (run_id, transition_id)."""
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
            artifacts=[],
            raw_outputs=[],
            logs=[],
            metrics={},
            errors=[],
            store_dir=str(store_dir),
        )
        return run_id

    def test_state_show_current_snapshot(self):
        """state should return the current observed state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            result = run_state_command(
                run_id=run_id,
                store_dir=str(store_dir),
                add_knowledge=None,
                add_open_question=None,
                add_artifact=None,
                add_prediction=None,
                add_branch=None,
            )
            assert result["state"]["state_id"].startswith("s_obs_")
            assert result["state"]["state_kind"] == "observed"
            assert "snapshot" in result["state"]
            assert result["state"]["snapshot"]["requirement"]["requirement_id"] == "req_test"

    def test_state_add_knowledge(self):
        """state --add-knowledge should append to snapshot.knowledge."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            result = run_state_command(
                run_id=run_id,
                store_dir=str(store_dir),
                add_knowledge=["tile size 32 improves latency"],
                add_open_question=None,
                add_artifact=None,
                add_prediction=None,
                add_branch=None,
            )
            knowledge = result["state"]["snapshot"]["knowledge"]
            assert len(knowledge) == 1
            assert knowledge[0]["summary"] == "tile size 32 improves latency"

    def test_state_add_open_question(self):
        """state --add-open-question should append to snapshot.open_questions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            result = run_state_command(
                run_id=run_id,
                store_dir=str(store_dir),
                add_knowledge=None,
                add_open_question=["memory bandwidth bottleneck?"],
                add_artifact=None,
                add_prediction=None,
                add_branch=None,
            )
            questions = result["state"]["snapshot"]["open_questions"]
            assert len(questions) == 1
            assert questions[0] == "memory bandwidth bottleneck?"

    def test_state_add_artifact(self):
        """state --add-artifact should append to snapshot.artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            result = run_state_command(
                run_id=run_id,
                store_dir=str(store_dir),
                add_knowledge=None,
                add_open_question=None,
                add_artifact=["profile:raw:raw/profile.txt"],
                add_prediction=None,
                add_branch=None,
            )
            artifacts = result["state"]["snapshot"]["artifacts"]
            assert len(artifacts) == 1
            assert artifacts[0]["artifact_id"] == "profile"
            assert artifacts[0]["artifact_type"] == "raw"
            assert artifacts[0]["path"] == "raw/profile.txt"

    def test_state_persists_after_save(self):
        """state update should persist after save and reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            run_state_command(
                run_id=run_id,
                store_dir=str(store_dir),
                add_knowledge=["speedup achieved"],
                add_open_question=None,
                add_artifact=None,
                add_prediction=None,
                add_branch=None,
            )

            from optagent.storage.jsonl import JsonlRunStore
            store = JsonlRunStore(store_dir)
            loaded = store.load_run(run_id)
            state = loaded.trace_dag.nodes[loaded.current_observed_state_id]
            assert len(state.snapshot.knowledge) == 1
            assert state.snapshot.knowledge[0].summary == "speedup achieved"

    def test_state_unknown_run_id(self):
        """state with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_state_command(
                    run_id="nonexistent",
                    store_dir=str(store_dir),
                    add_knowledge=None,
                    add_open_question=None,
                    add_artifact=None,
                    add_prediction=None,
                    add_branch=None,
                )

    def test_cli_parse_args_state(self):
        """argparse should correctly parse state subcommand."""
        args = parse_args(["state", "my_run"])
        assert args.command == "state"
        assert args.run_id == "my_run"

    def test_cli_parse_args_state_with_options(self):
        """argparse should handle all state options."""
        args = parse_args([
            "state", "my_run",
            "--add-knowledge", "k1",
            "--add-open-question", "q1",
            "--add-artifact", "a1:t1:p1",
            "--add-prediction", "pred1:s1",
            "--add-branch", "b1",
            "--store-dir", "/tmp/runs",
        ])
        assert args.add_knowledge == ["k1"]
        assert args.add_open_question == ["q1"]
        assert args.add_artifact == ["a1:t1:p1"]
        assert args.add_prediction == ["pred1:s1"]
        assert args.add_branch == ["b1"]
        assert args.store_dir == "/tmp/runs"

    def test_main_state_command(self, capsys):
        """main() should execute state and print JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            exit_code = main([
                "state", run_id,
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            state = json.loads(captured.out)
            assert state["state_id"].startswith("s_obs_")
            assert state["state_kind"] == "observed"

    def test_state_returns_json_serializable(self):
        """run_state_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id = self._create_run_with_observation(store_dir)

            result = run_state_command(
                run_id=run_id,
                store_dir=str(store_dir),
                add_knowledge=None,
                add_open_question=None,
                add_artifact=None,
                add_prediction=None,
                add_branch=None,
            )
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert parsed["state"]["state_id"].startswith("s_obs_")
