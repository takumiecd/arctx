"""Tests for optagent CLI list command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.list import run_list_command, cli_list
from optagent.cli.main import parse_args, main


class TestCliListCommand:
    """TDD for optagent list CLI."""

    def test_list_empty_store(self):
        """list on empty store should return empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            store_dir.mkdir()

            result = run_list_command(store_dir=str(store_dir))
            assert result["runs"] == []

    def test_list_returns_created_runs(self):
        """list should return all created runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"

            run_init_command(
                requirement_id="req_kernel",
                target_type="kernel",
                target_id="csc_linear",
                run_id="run_a",
                store_dir=str(store_dir),
            )
            run_init_command(
                requirement_id="req_code",
                target_type="code",
                target_id="module_b",
                run_id="run_b",
                store_dir=str(store_dir),
            )

            result = run_list_command(store_dir=str(store_dir))
            assert len(result["runs"]) == 2
            run_ids = {r["run_id"] for r in result["runs"]}
            assert run_ids == {"run_a", "run_b"}

    def test_list_includes_requirement_info(self):
        """list entries should include requirement metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"

            run_init_command(
                requirement_id="req_kernel",
                target_type="kernel",
                target_id="csc_linear",
                run_id="run_a",
                store_dir=str(store_dir),
            )

            result = run_list_command(store_dir=str(store_dir))
            assert len(result["runs"]) == 1
            entry = result["runs"][0]
            assert entry["run_id"] == "run_a"
            assert entry["requirement_id"] == "req_kernel"
            assert entry["target_type"] == "kernel"
            assert entry["target_id"] == "csc_linear"
            assert "current_observed_state_id" not in entry

    def test_list_ignores_non_run_directories(self):
        """list should ignore directories without run.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            store_dir.mkdir()
            (store_dir / "not_a_run").mkdir()

            result = run_list_command(store_dir=str(store_dir))
            assert result["runs"] == []

    def test_cli_parse_args_list(self):
        """argparse should correctly parse list subcommand."""
        args = parse_args(["list"])
        assert args.command == "list"
        assert args.store_dir == ".optagent/runs"

    def test_cli_parse_args_list_with_store_dir(self):
        """argparse should handle --store-dir for list."""
        args = parse_args(["list", "--store-dir", "/tmp/runs"])
        assert args.store_dir == "/tmp/runs"

    def test_main_list_command(self, capsys):
        """main() should execute list and print runs JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_init_command(
                requirement_id="req_test",
                target_type="code",
                target_id="module_a",
                run_id="run_001",
                store_dir=str(store_dir),
            )

            exit_code = main([
                "list",
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            runs = json.loads(captured.out)
            assert len(runs) == 1
            assert runs[0]["run_id"] == "run_001"

    def test_list_returns_json_serializable(self):
        """run_list_command result must be JSON serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_init_command(
                requirement_id="req_test",
                target_type="code",
                target_id="module_a",
                run_id="run_001",
                store_dir=str(store_dir),
            )

            result = run_list_command(store_dir=str(store_dir))
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert len(parsed["runs"]) == 1
