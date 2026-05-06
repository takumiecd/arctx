"""Tests for optagent CLI derive command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.derive import run_derive_command, cli_derive
from optagent.cli.main import parse_args, main


class TestCliDeriveCommand:
    """TDD for optagent derive CLI."""

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
        observe_result = run_observe_command(
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
        return run_id, observe_result["transition"]["transition_id"]

    def test_derive_attaches_finding(self):
        """derive should attach a DerivedRecord to an observed transition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, transition_id = self._create_run_with_observation(store_dir)

            result = run_derive_command(
                run_id=run_id,
                transition_id=transition_id,
                derived_type="finding",
                payload={"text": "latency improved from 2.1ms to 1.5ms"},
                derived_id=None,
                generator="cli",
                confidence=None,
                store_dir=str(store_dir),
            )
            assert result["record"]["derived_type"] == "finding"
            assert result["record"]["payload"]["text"] == "latency improved from 2.1ms to 1.5ms"
            assert result["record"]["source_transition_id"] == transition_id
            assert result["record"]["generator"] == "cli"
            assert result["record"]["derived_id"].startswith("d_")

    def test_derive_unknown_transition(self):
        """derive with unknown transition_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, _ = self._create_run_with_observation(store_dir)
            with pytest.raises(KeyError):
                run_derive_command(
                    run_id=run_id,
                    transition_id="nonexistent",
                    derived_type="finding",
                    payload={"text": "..."},
                    derived_id=None,
                    generator="cli",
                    confidence=None,
                    store_dir=str(store_dir),
                )

    def test_derive_with_explicit_id(self):
        """derive --id should set explicit derived_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, transition_id = self._create_run_with_observation(store_dir)

            result = run_derive_command(
                run_id=run_id,
                transition_id=transition_id,
                derived_type="evidence",
                payload={"correctness": "true"},
                derived_id="d_custom_001",
                generator="cli",
                confidence=0.95,
                store_dir=str(store_dir),
            )
            assert result["record"]["derived_id"] == "d_custom_001"
            assert result["record"]["confidence"] == 0.95

    def test_derive_persists_after_save(self):
        """derive should persist after save and reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, transition_id = self._create_run_with_observation(store_dir)

            run_derive_command(
                run_id=run_id,
                transition_id=transition_id,
                derived_type="finding",
                payload={"text": "speedup achieved"},
                derived_id=None,
                generator="cli",
                confidence=None,
                store_dir=str(store_dir),
            )

            from optagent.storage.jsonl import JsonlRunStore
            store = JsonlRunStore(store_dir)
            loaded = store.load_run(run_id)
            transition = loaded.trace_dag.transitions[transition_id]
            assert len(transition.derived_records) == 1
            assert transition.derived_records[0].payload["text"] == "speedup achieved"

    def test_cli_parse_args_derive(self):
        """argparse should correctly parse derive subcommand."""
        args = parse_args(["derive", "t_obs_0001", "--run", "my_run"])
        assert args.command == "derive"
        assert args.run == "my_run"
        assert args.transition_id == "t_obs_0001"
        assert args.derived_type == "finding"

    def test_cli_parse_args_derive_with_options(self):
        """argparse should handle all derive options."""
        args = parse_args([
            "derive", "t_obs_0001", "--run", "my_run",
            "--type", "evidence",
            "--id", "d_custom",
            "--text", "latency improved",
            "--confidence", "0.9",
            "--store-dir", "/tmp/runs",
        ])
        assert args.derived_type == "evidence"
        assert args.derived_id == "d_custom"
        assert args.text == "latency improved"
        assert args.confidence == 0.9
        assert args.store_dir == "/tmp/runs"

    def test_main_derive_command(self, capsys):
        """main() should execute derive and print record JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, transition_id = self._create_run_with_observation(store_dir)

            exit_code = main([
                "derive", transition_id, "--run", run_id,
                "--text", "test derive",
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            record = json.loads(captured.out)
            assert record["derived_type"] == "finding"
            assert record["payload"]["text"] == "test derive"

    def test_derive_returns_json_serializable(self):
        """run_derive_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, transition_id = self._create_run_with_observation(store_dir)

            result = run_derive_command(
                run_id=run_id,
                transition_id=transition_id,
                derived_type="finding",
                payload={"text": "derive text"},
                derived_id=None,
                generator="cli",
                confidence=None,
                store_dir=str(store_dir),
            )
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert parsed["record"]["derived_id"].startswith("d_")
