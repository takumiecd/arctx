"""Phase 1 git-native storage: run data lives inside the repository.

Default layout is ``<repo_root>/.arctx/runs/<run_id>/``; ``ARCTX_HOME`` remains
an explicit override. ``arctx init`` also drops the git metadata that makes the
directory merge correctly (``merge=union``) and keeps derived files out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arctx.paths import GITATTRIBUTES_LINES, GITIGNORE_LINES
from arctx_cli.commands.init import run_init_command
from arctx_cli.paths import resolve_store_dir, runs_dir, write_repo_git_metadata


def _repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def in_repo(tmp_path, monkeypatch):
    """A repo checkout with no ARCTX_HOME override in effect."""
    monkeypatch.delenv("ARCTX_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    repo = _repo(tmp_path)
    monkeypatch.chdir(repo)
    return repo


# ---------------------------------------------------------------------------
# store dir resolution
# ---------------------------------------------------------------------------


def test_store_dir_defaults_to_in_repo(in_repo):
    assert runs_dir() == in_repo / ".arctx" / "runs"
    assert resolve_store_dir() == str(in_repo / ".arctx" / "runs")


def test_store_dir_resolves_from_a_subdirectory(in_repo):
    nested = in_repo / "packages" / "deep"
    nested.mkdir(parents=True)
    assert runs_dir(nested) == in_repo / ".arctx" / "runs"


def test_arctx_home_env_overrides_in_repo(in_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "home"))
    assert runs_dir() == tmp_path / "home" / "runs"


def test_outside_a_repo_falls_back_to_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("ARCTX_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    outside = tmp_path / "no_repo"
    outside.mkdir()
    monkeypatch.chdir(outside)
    assert runs_dir() == tmp_path / "xdg" / "arctx" / "runs"


# ---------------------------------------------------------------------------
# arctx init
# ---------------------------------------------------------------------------


def test_init_creates_run_inside_the_repo(in_repo):
    result = run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="t",
        run_id="run_inrepo",
        store_dir=None,
    )
    run_dir = in_repo / ".arctx" / "runs" / "run_inrepo"
    assert result["store_dir"] == str(in_repo / ".arctx" / "runs")
    assert (run_dir / "run.json").exists()
    assert (run_dir / "nodes.jsonl").exists()
    # The active-run pointer still lives in the gitdir, untracked by git.
    assert (in_repo / ".git" / "arctx-id").read_text(encoding="utf-8").strip() == "run_inrepo"


def test_init_writes_gitattributes_and_gitignore(in_repo):
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="t",
        run_id="run_attrs",
        store_dir=None,
    )
    attrs = (in_repo / ".arctx" / ".gitattributes").read_text(encoding="utf-8")
    assert attrs.splitlines() == ["* linguist-generated=true", "*.jsonl merge=union"]

    ignore = (in_repo / ".arctx" / ".gitignore").read_text(encoding="utf-8").splitlines()
    # Derived local files must never be committed.
    assert "run.cache.pkl" in ignore
    assert "run.db" in ignore


def test_git_metadata_is_idempotent(in_repo):
    write_repo_git_metadata(in_repo)
    write_repo_git_metadata(in_repo)
    write_repo_git_metadata(in_repo)

    attrs = (in_repo / ".arctx" / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert attrs == list(GITATTRIBUTES_LINES)
    ignore = (in_repo / ".arctx" / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ignore == list(GITIGNORE_LINES)


def test_git_metadata_preserves_user_lines(in_repo):
    arctx_dir = in_repo / ".arctx"
    arctx_dir.mkdir()
    (arctx_dir / ".gitattributes").write_text("*.bin binary\n", encoding="utf-8")

    write_repo_git_metadata(in_repo)

    lines = (arctx_dir / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "*.bin binary"
    for expected in GITATTRIBUTES_LINES:
        assert expected in lines


def test_generated_gitignore_covers_the_derived_files(in_repo):
    """Every file the store writes that is not jsonl/json must be ignored."""
    import fnmatch

    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="t",
        run_id="run_derived",
        store_dir=None,
    )
    run_dir = in_repo / ".arctx" / "runs" / "run_derived"
    patterns = [
        line
        for line in (in_repo / ".arctx" / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    for entry in run_dir.iterdir():
        if entry.suffix in {".json", ".jsonl"}:
            continue
        assert any(
            fnmatch.fnmatch(entry.name, pat) for pat in patterns
        ), f"{entry.name} is neither canon nor ignored"
