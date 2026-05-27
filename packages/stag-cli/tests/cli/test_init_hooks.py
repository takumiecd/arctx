"""Tests for stag init hook installation behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path

from stag_cli.commands.init import run_init_command


def _init_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(path), capture_output=True, check=True,
    )
    return path


def _store_dir(tmp_path: Path) -> str:
    return str(tmp_path / "stag_home" / "runs")


class TestInitHooks:
    def test_init_in_git_repo_installs_hook(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)

        result = run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_hook_test",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
            no_hooks=False,
        )

        assert result.get("hook_path") is not None
        hook_path = Path(result["hook_path"])
        assert hook_path.exists()

    def test_init_with_no_hooks_skips_install(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)

        result = run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_no_hooks",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
            no_hooks=True,
        )

        assert result.get("hook_path") is None
        hook_path = repo / ".git" / "hooks" / "post-rewrite"
        assert not hook_path.exists()

    def test_init_outside_git_repo_skips_hook(self, tmp_path, monkeypatch):
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()
        monkeypatch.chdir(non_repo)

        result = run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_outside_git",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
            no_hooks=False,
        )

        # No hook_path — we're not in a git repo.
        assert result.get("hook_path") is None

    def test_init_does_not_overwrite_existing_hook(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)

        # Pre-create a hook.
        hook_path = repo / ".git" / "hooks" / "post-rewrite"
        hook_path.write_text("# existing\n", encoding="utf-8")

        result = run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_existing_hook",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
            no_hooks=False,
        )

        # Skipped — existing hook preserved.
        assert result.get("hook_path") is None
        assert result.get("hook_warning") is not None
        assert hook_path.read_text(encoding="utf-8") == "# existing\n"
