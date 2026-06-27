"""Integration tests for `arctx git repo` / `arctx git init` with real repos."""

from __future__ import annotations

import subprocess
from pathlib import Path

from arctx_cli.commands.init import run_init_command
from arctx_cli.context import resolve_store
from arctx_cli.ext.git.repo import run_repo_add


def _init_git_repo(path: Path, *, remote: str | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=str(path),
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path),
                   capture_output=True, check=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=str(path),
                   capture_output=True, check=True)
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(path),
                   capture_output=True, check=True)
    if remote is not None:
        subprocess.run(["git", "remote", "add", "origin", remote], cwd=str(path),
                       capture_output=True, check=True)
    return path


def _store_dir(tmp_path: Path) -> str:
    return str(tmp_path / "arctx_home" / "runs")


def _init_run(tmp_path: Path, run_id: str) -> None:
    run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        extensions=["git"],
    )


class TestRepoAdd:
    def test_add_registers_repo_and_persists(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo", remote="git@github.com:me/proj.git")
        monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "arctx_home"))
        monkeypatch.chdir(repo)
        _init_run(tmp_path, "run_a")

        result = run_repo_add(
            repo_path=str(repo),
            slug=None,
            run_id="run_a",
            store_dir=_store_dir(tmp_path),
            user_id="alice",
            lane_id="ws",
            install_hooks=False,
        )
        assert result["repo_id"].startswith("repo_")
        assert result["slug"] == "me/proj"
        assert result["canonical"] == "github.com/me/proj"

        # Reload from store: registry survived persistence.
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_a")
        from arctx.ext.git.registry import list_repos

        repos = list_repos(handle.run_graph)
        assert [r.repo_id for r in repos] == [result["repo_id"]]
        # .arctx-id pointer written for this repo.
        from arctx.paths import read_arctx_id

        assert read_arctx_id(repo) == "run_a"

    def test_slug_override(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo", remote="git@github.com:me/proj.git")
        monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "arctx_home"))
        monkeypatch.chdir(repo)
        _init_run(tmp_path, "run_b")

        result = run_repo_add(
            repo_path=str(repo),
            slug="custom/name",
            run_id="run_b",
            store_dir=_store_dir(tmp_path),
            user_id="alice",
            lane_id="ws",
            install_hooks=False,
        )
        assert result["slug"] == "custom/name"

    def test_idempotent_re_add(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo", remote="git@github.com:me/proj.git")
        monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "arctx_home"))
        monkeypatch.chdir(repo)
        _init_run(tmp_path, "run_c")

        first = run_repo_add(
            repo_path=str(repo), slug=None, run_id="run_c",
            store_dir=_store_dir(tmp_path), user_id="alice",
            lane_id="ws", install_hooks=False,
        )
        second = run_repo_add(
            repo_path=str(repo), slug=None, run_id="run_c",
            store_dir=_store_dir(tmp_path), user_id="alice",
            lane_id="ws", install_hooks=False,
        )
        assert first["repo_id"] == second["repo_id"]

        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_c")
        from arctx.ext.git.registry import list_repos

        assert len(list_repos(handle.run_graph)) == 1
