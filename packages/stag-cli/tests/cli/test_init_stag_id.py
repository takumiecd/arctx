"""Integration tests for S1: stag-id based run resolution."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from stag_cli.commands.init import run_init_command
from stag_cli.commands.use import run_use_command
from stag_cli.context import resolve_run_id
from stag_cli.paths import read_stag_id, write_stag_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_git_repo(tmp_path: Path) -> Path:
    """Create a minimal fake git repo (a .git directory) under tmp_path."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def _stag_home(tmp_path: Path) -> Path:
    return tmp_path / "stag_home"


def _store_dir(tmp_path: Path) -> str:
    return str(_stag_home(tmp_path) / "runs")


# ---------------------------------------------------------------------------
# stag init writes .stag-id and creates run in STAG_HOME/runs
# ---------------------------------------------------------------------------


def test_init_writes_stag_id(tmp_path, monkeypatch):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
    monkeypatch.chdir(repo)

    result = run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="run_s1",
        store_dir=_store_dir(tmp_path),
    )

    assert result["run_id"] == "run_s1"
    stag_id_file = repo / ".git" / "stag-id"
    assert stag_id_file.exists(), "stag-id should be written under <gitdir>"
    assert read_stag_id(repo) == "run_s1"
    # Ensure no legacy file is left in the repo working tree.
    assert not (repo / ".stag-id").exists()


def test_init_creates_run_under_stag_home(tmp_path, monkeypatch):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
    monkeypatch.chdir(repo)

    run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="run_s1",
        store_dir=_store_dir(tmp_path),
    )

    run_dir = _stag_home(tmp_path) / "runs" / "run_s1"
    assert run_dir.exists(), "run directory should exist under STAG_HOME/runs"


def test_init_without_git_repo_still_creates_run(tmp_path, monkeypatch):
    """When not inside a git repo, init should succeed without writing stag-id."""
    monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
    # tmp_path has no .git — find_repo_root should fail silently
    monkeypatch.chdir(tmp_path)

    result = run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="run_no_git",
        store_dir=_store_dir(tmp_path),
    )

    assert result["run_id"] == "run_no_git"
    assert result["stag_id_path"] is None
    assert not (tmp_path / ".stag-id").exists()


# ---------------------------------------------------------------------------
# resolve_run_id resolves from <gitdir>/stag-id
# ---------------------------------------------------------------------------


def test_resolve_run_id_from_stag_id(tmp_path, monkeypatch):
    repo = _fake_git_repo(tmp_path)
    write_stag_id(repo, "run_from_stag_id")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("STAG_RUN_ID", raising=False)

    result = resolve_run_id(None)
    assert result == "run_from_stag_id"


def test_resolve_run_id_explicit_takes_priority(tmp_path, monkeypatch):
    repo = _fake_git_repo(tmp_path)
    write_stag_id(repo, "run_from_stag_id")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("STAG_RUN_ID", raising=False)

    result = resolve_run_id("explicit_run")
    assert result == "explicit_run"


def test_resolve_run_id_env_takes_priority_over_stag_id(tmp_path, monkeypatch):
    repo = _fake_git_repo(tmp_path)
    write_stag_id(repo, "run_from_stag_id")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("STAG_RUN_ID", "run_from_env")

    result = resolve_run_id(None)
    assert result == "run_from_env"


def test_resolve_run_id_raises_when_no_stag_id(tmp_path, monkeypatch):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("STAG_RUN_ID", raising=False)

    with pytest.raises(RuntimeError, match="no current run set"):
        resolve_run_id(None)


# ---------------------------------------------------------------------------
# stag use: writes stag-id in git repo
# ---------------------------------------------------------------------------


def test_use_writes_stag_id(tmp_path, monkeypatch):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
    monkeypatch.chdir(repo)

    # First create a run
    run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="run_a",
        store_dir=_store_dir(tmp_path),
    )
    run_init_command(
        requirement_id="req2",
        target_type="task",
        target_id="t",
        run_id="run_b",
        store_dir=_store_dir(tmp_path),
    )

    # Switch to run_b
    run_use_command(run_id="run_b", store_dir=_store_dir(tmp_path))
    assert read_stag_id(repo) == "run_b"

    # Switch back to run_a
    run_use_command(run_id="run_a", store_dir=_store_dir(tmp_path))
    assert read_stag_id(repo) == "run_a"


def test_use_raises_for_unknown_run(tmp_path, monkeypatch):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
    monkeypatch.chdir(repo)

    with pytest.raises(KeyError, match="unknown run_id"):
        run_use_command(run_id="no_such_run", store_dir=_store_dir(tmp_path))


# ---------------------------------------------------------------------------
# STAG_HOME env overrides run storage location end-to-end
# ---------------------------------------------------------------------------


def test_stag_home_env_controls_store_location(tmp_path, monkeypatch):
    repo = _fake_git_repo(tmp_path)
    custom_home = tmp_path / "my_stag"
    monkeypatch.setenv("STAG_HOME", str(custom_home))
    monkeypatch.chdir(repo)

    run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="run_custom",
        store_dir=str(custom_home / "runs"),
    )

    assert (custom_home / "runs" / "run_custom").exists()
    assert read_stag_id(repo) == "run_custom"
