"""Unit tests for arctx.cli.paths — ARCTX_HOME resolution and arctx-id helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from arctx_cli.paths import (
    find_repo_root,
    read_arctx_id,
    resolve_git_dir,
    resolve_arctx_home,
    resolve_store_dir,
    runs_dir,
    arctx_id_path,
    write_arctx_id,
)


# ---------------------------------------------------------------------------
# resolve_arctx_home
# ---------------------------------------------------------------------------


def test_resolve_arctx_home_uses_arctx_home_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "custom_arctx"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = resolve_arctx_home()
    assert result == tmp_path / "custom_arctx"


def test_resolve_arctx_home_uses_xdg_data_home(tmp_path, monkeypatch):
    monkeypatch.delenv("ARCTX_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    result = resolve_arctx_home()
    assert result == tmp_path / "xdg" / "arctx"


def test_resolve_arctx_home_falls_back_to_local_share(monkeypatch):
    monkeypatch.delenv("ARCTX_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = resolve_arctx_home()
    assert result == Path.home() / ".local/share/arctx"


def test_arctx_home_priority_over_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "arctx_home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    result = resolve_arctx_home()
    assert result == tmp_path / "arctx_home"


# ---------------------------------------------------------------------------
# runs_dir / resolve_store_dir
# ---------------------------------------------------------------------------


def test_runs_dir_is_under_arctx_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "arctx"))
    assert runs_dir() == tmp_path / "arctx"/ "runs"


def test_resolve_store_dir_returns_str(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "arctx"))
    result = resolve_store_dir()
    assert isinstance(result, str)
    assert result.endswith("runs")


# ---------------------------------------------------------------------------
# arctx_id_path / resolve_git_dir
# ---------------------------------------------------------------------------


def test_arctx_id_path_is_inside_gitdir(tmp_path):
    (tmp_path / ".git").mkdir()
    assert arctx_id_path(tmp_path) == tmp_path / ".git" / "arctx-id"


def test_resolve_git_dir_follows_worktree_pointer(tmp_path):
    # Simulate a linked worktree: .git is a *file* containing
    # ``gitdir: <path>``.
    main_repo = tmp_path / "main"
    main_repo.mkdir()
    real_gitdir = main_repo / ".git" / "worktrees" / "wt1"
    real_gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt1"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {real_gitdir}\n", encoding="utf-8"
    )
    assert resolve_git_dir(worktree) == real_gitdir
    assert arctx_id_path(worktree) == real_gitdir / "arctx-id"


# ---------------------------------------------------------------------------
# read_arctx_id / write_arctx_id
# ---------------------------------------------------------------------------


def test_read_arctx_id_returns_none_when_missing(tmp_path):
    (tmp_path / ".git").mkdir()
    assert read_arctx_id(tmp_path) is None


def test_write_and_read_arctx_id_roundtrip(tmp_path):
    (tmp_path / ".git").mkdir()
    run_id = "run_abc123"
    write_arctx_id(tmp_path, run_id)
    assert read_arctx_id(tmp_path) == run_id


def test_write_arctx_id_includes_trailing_newline(tmp_path):
    (tmp_path / ".git").mkdir()
    write_arctx_id(tmp_path, "run_xyz")
    content = (tmp_path / ".git" / "arctx-id").read_text(encoding="utf-8")
    assert content == "run_xyz\n"


def test_read_arctx_id_strips_whitespace(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "arctx-id").write_text(
        "  run_trimmed  \n", encoding="utf-8"
    )
    assert read_arctx_id(tmp_path) == "run_trimmed"


def test_read_arctx_id_returns_none_for_empty_file(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "arctx-id").write_text("", encoding="utf-8")
    assert read_arctx_id(tmp_path) is None


def test_read_arctx_id_migrates_legacy_file(tmp_path):
    """Legacy ``<repo_root>/.arctx-id`` files are migrated on read."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".arctx-id").write_text("run_legacy\n", encoding="utf-8")
    assert read_arctx_id(tmp_path) == "run_legacy"
    # After migration, the canonical location holds the id and the
    # legacy file is gone.
    assert (tmp_path / ".git" / "arctx-id").read_text(encoding="utf-8").strip() == "run_legacy"
    assert not (tmp_path / ".arctx-id").exists()


# ---------------------------------------------------------------------------
# find_repo_root
# ---------------------------------------------------------------------------


def test_find_repo_root_finds_git_dir(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    assert find_repo_root(tmp_path) == tmp_path


def test_find_repo_root_walks_up(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == tmp_path


def test_find_repo_root_raises_outside_repo(tmp_path):
    # tmp_path has no .git; walk up from a deeply nested dir that also has none
    nested = tmp_path / "no_git_here"
    nested.mkdir()
    with pytest.raises(RuntimeError, match="not inside a git repository"):
        find_repo_root(nested)
