"""Tests for optagent CLI init command."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import cli_init, run_init_command
from optagent.cli.main import parse_args, main
from optagent.storage.jsonl import JsonlRunStore


class TestCliInitCommand:
    """TDD for optagent init CLI."""

    def test_init_creates_run_directory(self):
        """init should create a run directory under store_dir."""
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
            run_path = store_dir / run_id
            assert run_path.exists()
            assert (run_path / "run.json").exists()
            assert (run_path / "states.jsonl").exists()

    def test_init_uses_explicit_run_id(self):
        """--run-id should be used as the run directory name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            result = run_init_command(
                requirement_id="req_test",
                target_type="code",
                target_id="module_a",
                run_id="my_run_001",
                store_dir=str(store_dir),
            )
            assert result["run_id"] == "my_run_001"
            assert (store_dir / "my_run_001").exists()

    def test_init_saves_requirement_fields(self):
        """Requirement fields should be preserved in the saved run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_init_command(
                requirement_id="req_kernel",
                target_type="kernel",
                target_id="csc_linear",
                run_id=None,
                store_dir=str(store_dir),
            )
            # Find the created run directory
            run_dirs = list(store_dir.iterdir())
            assert len(run_dirs) == 1
            run_json = run_dirs[0] / "run.json"
            data = json.loads(run_json.read_text())
            assert data["requirement"]["requirement_id"] == "req_kernel"
            assert data["requirement"]["target_type"] == "kernel"
            assert data["requirement"]["target_id"] == "csc_linear"

    def test_init_returns_run_id_in_result(self):
        """run_init_command should return the run_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            result = run_init_command(
                requirement_id="req_test",
                target_type="code",
                target_id="module_a",
                run_id=None,
                store_dir=str(store_dir),
            )
            assert "run_id" in result
            assert isinstance(result["run_id"], str)
            assert result["run_id"].startswith("run_")

    def test_init_with_custom_store_dir(self):
        """--store-dir should change where the run is saved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = Path(tmpdir) / "custom_runs"
            result = run_init_command(
                requirement_id="req_test",
                target_type="code",
                target_id="module_a",
                run_id=None,
                store_dir=str(custom_dir),
            )
            assert (custom_dir / result["run_id"]).exists()

    def test_cli_parse_args_init(self):
        """argparse should correctly parse init subcommand."""
        args = parse_args(["init", "req_test"])
        assert args.command == "init"
        assert args.requirement_id == "req_test"
        assert args.target_type == "code"
        assert args.target_id is None
        assert args.run_id is None

    def test_cli_parse_args_init_with_options(self):
        """argparse should handle all init options."""
        args = parse_args([
            "init", "req_kernel",
            "--target-type", "kernel",
            "--target-id", "csc_linear",
            "--run-id", "demo",
            "--store-dir", "/tmp/runs",
        ])
        assert args.command == "init"
        assert args.requirement_id == "req_kernel"
        assert args.target_type == "kernel"
        assert args.target_id == "csc_linear"
        assert args.run_id == "demo"
        assert args.store_dir == "/tmp/runs"

    def test_main_init_command(self, capsys):
        """main() should execute init and print run_id to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            exit_code = main([
                "init", "req_test",
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            run_id = captured.out.strip()
            assert run_id.startswith("run_")
            assert (store_dir / run_id).exists()

    def test_init_idempotency_same_run_id(self):
        """Calling init twice with same run_id should raise or overwrite cleanly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_init_command(
                requirement_id="req_test",
                target_type="code",
                target_id="module_a",
                run_id="same_id",
                store_dir=str(store_dir),
            )
            # Second call with same run_id
            with pytest.raises(FileExistsError):
                run_init_command(
                    requirement_id="req_test",
                    target_type="code",
                    target_id="module_a",
                    run_id="same_id",
                    store_dir=str(store_dir),
                )
