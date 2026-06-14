"""Tests for the ``arctx migrate`` command (jsonl -> sqlite)."""

from __future__ import annotations

from pathlib import Path

from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.migrate import run_migrate_command


def _init(store_dir: str, run_id: str = "mig_run") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=store_dir,
    )


def test_migrate_with_explicit_store_dir(tmp_path):
    store_dir = str(tmp_path / "runs")
    _init(store_dir, run_id="r1")

    result = run_migrate_command(
        to="sqlite", store_dir=store_dir, run_id="r1", all_runs=False, force=False
    )

    assert result == {"migrated": ["r1"], "skipped": [], "failed": []}
    assert (Path(store_dir) / "r1" / "run.db").exists()


def test_migrate_defaults_store_dir_to_arctx_home(tmp_path, monkeypatch):
    """store_dir=None must resolve to <ARCTX_HOME>/runs instead of crashing."""
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    from arctx_cli.paths import resolve_store_dir

    store_dir = resolve_store_dir()
    _init(store_dir, run_id="r2")

    result = run_migrate_command(
        to="sqlite", store_dir=None, run_id="r2", all_runs=False, force=False
    )

    assert result == {"migrated": ["r2"], "skipped": [], "failed": []}
    assert (Path(store_dir) / "r2" / "run.db").exists()
