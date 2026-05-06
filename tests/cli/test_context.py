"""Tests for optagent CLI use/current commands."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.use import run_use_command
from optagent.cli.commands.current import run_current_command
from optagent.cli.context import save_current_run, load_current_run, resolve_run_id, current_path
from optagent.cli.main import parse_args, main


class TestCliContext:
    """TDD for optagent CLI current-run context."""

    def test_save_and_load_current_run(self):
        """save_current_run / load_current_run should round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            save_current_run("demo", str(store_dir))
            assert load_current_run(str(store_dir)) == "demo"

    def test_load_current_run_missing(self):
        """load_current_run without marker should raise RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(RuntimeError):
                load_current_run(str(store_dir))

    def test_resolve_run_id_explicit(self):
        """resolve_run_id should prefer explicit run_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            assert resolve_run_id("explicit", str(store_dir)) == "explicit"

    def test_resolve_run_id_env(self):
        """resolve_run_id should fall back to OPTAGENT_RUN_ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            os.environ["OPTAGENT_RUN_ID"] = "env_run"
            try:
                assert resolve_run_id(None, str(store_dir)) == "env_run"
            finally:
                del os.environ["OPTAGENT_RUN_ID"]

    def test_resolve_run_id_current_file(self):
        """resolve_run_id should fall back to current.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            save_current_run("file_run", str(store_dir))
            assert resolve_run_id(None, str(store_dir)) == "file_run"

    def test_resolve_run_id_no_source(self):
        """resolve_run_id with no source should raise RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(RuntimeError):
                resolve_run_id(None, str(store_dir))

    def test_use_sets_current_run(self):
        """use should persist run_id to current.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_init_command(
                requirement_id="req_test",
                target_type="code",
                target_id="module_a",
                run_id="demo",
                store_dir=str(store_dir),
            )
            result = run_use_command(run_id="demo", store_dir=str(store_dir))
            assert result["run_id"] == "demo"
            assert load_current_run(str(store_dir)) == "demo"

    def test_use_unknown_run_id(self):
        """use with unknown run_id should raise KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(KeyError):
                run_use_command(run_id="nonexistent", store_dir=str(store_dir))

    def test_current_shows_run_id(self):
        """current should return the persisted run_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            save_current_run("demo", str(store_dir))
            result = run_current_command(store_dir=str(store_dir))
            assert result["run_id"] == "demo"

    def test_current_no_current_run(self):
        """current without marker should raise RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            with pytest.raises(RuntimeError):
                run_current_command(store_dir=str(store_dir))

    def test_cli_parse_args_use(self):
        """argparse should correctly parse use subcommand."""
        args = parse_args(["use", "my_run"])
        assert args.command == "use"
        assert args.run_id == "my_run"

    def test_cli_parse_args_current(self):
        """argparse should correctly parse current subcommand."""
        args = parse_args(["current"])
        assert args.command == "current"
        assert args.json_output is False

    def test_cli_parse_args_current_json(self):
        """argparse should handle --json for current."""
        args = parse_args(["current", "--json"])
        assert args.json_output is True

    def test_main_use_command(self, capsys):
        """main() should execute use and print run_id to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_init_command(
                requirement_id="req_test",
                target_type="code",
                target_id="module_a",
                run_id="demo",
                store_dir=str(store_dir),
            )
            exit_code = main(["use", "demo", "--store-dir", str(store_dir)])
            assert exit_code == 0
            captured = capsys.readouterr()
            assert captured.out.strip() == "demo"

    def test_main_current_command(self, capsys):
        """main() should execute current and print run_id to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            save_current_run("demo", str(store_dir))
            exit_code = main(["current", "--store-dir", str(store_dir)])
            assert exit_code == 0
            captured = capsys.readouterr()
            assert captured.out.strip() == "demo"

    def test_main_current_command_json(self, capsys):
        """main() should execute current --json and print JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            save_current_run("demo", str(store_dir))
            exit_code = main(["current", "--json", "--store-dir", str(store_dir)])
            assert exit_code == 0
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["run_id"] == "demo"
