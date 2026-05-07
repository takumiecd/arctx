"""Tests for optagent CLI snapshot command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.derive import run_derive_command
from optagent.cli.commands.snapshot import run_snapshot_command, cli_snapshot
from optagent.cli.main import parse_args, main


class TestCliSnapshotCommand:
    """TDD for optagent snapshot CLI."""

    def _create_run_with_history(self, store_dir: Path) -> tuple[str, str]:
        """Helper: create run with plan, observe, derive → return (run_id, transition_id)."""
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
        observe_result = run_observe_command(
            run_id=run_id,
            plan_id=plan_result["plans"][0]["plan_id"],
            result_id="r_0001",
            status="completed",
            artifacts=["build.log"],
            raw_outputs=["benchmark.txt"],
            logs=["stderr.log"],
            metrics={"speedup": 1.15},
            errors=[],
            store_dir=str(store_dir),
        )
        transition_id = observe_result["transition"]["transition_id"]
        run_derive_command(
            run_id=run_id,
            transition_id=transition_id,
            derived_type="finding",
            payload={"text": "latency improved"},
            derived_id=None,
            generator="cli",
            confidence=None,
            store_dir=str(store_dir),
        )
        return run_id, transition_id

    def test_snapshot_show_state(self):
        """snapshot should return the requested state snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, _ = self._create_run_with_history(store_dir)

            result = run_snapshot_command(
                run_id=run_id,
                state_id="s_obs_0001",
                rebuild=False,
                store_dir=str(store_dir),
            )
            assert result["state_id"].startswith("s_obs_")
            assert "snapshot" in result

    def test_snapshot_rebuild_from_derived(self):
        """snapshot --rebuild should regenerate snapshot from trace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, transition_id = self._create_run_with_history(store_dir)

            result = run_snapshot_command(
                run_id=run_id,
                state_id="s_obs_0001",
                rebuild=True,
                store_dir=str(store_dir),
            )
            snapshot = result["snapshot"]
            # Derived findings should become knowledge
            assert len(snapshot["knowledge"]) >= 1
            assert snapshot["knowledge"][0]["summary"] == "latency improved"
            # ActionResult artifacts should become ArtifactRefs
            artifact_ids = {a["artifact_id"] for a in snapshot["artifacts"]}
            assert "build.log" in artifact_ids or "benchmark.txt" in artifact_ids or "stderr.log" in artifact_ids

    def test_snapshot_rebuild_persists(self):
        """snapshot --rebuild should persist after save and reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, _ = self._create_run_with_history(store_dir)

            run_snapshot_command(
                run_id=run_id,
                state_id="s_obs_0001",
                rebuild=True,
                store_dir=str(store_dir),
            )

            from optagent.storage.jsonl import JsonlRunStore
            store = JsonlRunStore(store_dir)
            loaded = store.load_run(run_id)
            state = loaded.trace_dag.nodes["s_obs_0001"]
            assert len(state.snapshot.knowledge) >= 1
            assert state.snapshot.knowledge[0].summary == "latency improved"

    def test_snapshot_unknown_run_id(self):
        """snapshot with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_snapshot_command(
                    run_id="nonexistent",
                    state_id="s_obs_0001",
                    rebuild=False,
                    store_dir=str(store_dir),
                )

    def test_cli_parse_args_snapshot(self):
        """argparse should correctly parse snapshot subcommand."""
        args = parse_args(["snapshot", "--run", "my_run"])
        assert args.command == "snapshot"
        assert args.run == "my_run"
        assert args.rebuild is False
        assert args.state_id is None

    def test_cli_parse_args_snapshot_rebuild(self):
        """argparse should handle --rebuild and --state-id."""
        args = parse_args([
            "snapshot", "--run", "my_run",
            "--rebuild",
            "--state-id", "s_obs_0001",
            "--store-dir", "/tmp/runs",
        ])
        assert args.rebuild is True
        assert args.state_id == "s_obs_0001"
        assert args.store_dir == "/tmp/runs"

    def test_main_snapshot_command(self, capsys):
        """main() should execute snapshot and print JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, _ = self._create_run_with_history(store_dir)

            exit_code = main([
                "snapshot", "--run", run_id,
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            result = json.loads(captured.out)
            assert result["state_id"].startswith("s_obs_")
            assert "snapshot" in result

    def test_snapshot_returns_json_serializable(self):
        """run_snapshot_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, _ = self._create_run_with_history(store_dir)

            result = run_snapshot_command(
                run_id=run_id,
                state_id="s_obs_0001",
                rebuild=True,
                store_dir=str(store_dir),
            )
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert parsed["state_id"].startswith("s_obs_")
