"""Tests for arctx hook install."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

from arctx_cli.ext.git.hook import run_hook_install


def _init_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True, check=True)
    return path


class TestHookInstall:
    def test_install_creates_post_rewrite_hook(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        result = run_hook_install(repo_path=repo, force=False)

        assert result["status"] == "installed"
        hook_path = Path(result["hook_path"])
        assert hook_path.exists()

    def test_installed_hook_is_executable(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        result = run_hook_install(repo_path=repo, force=False)

        hook_path = Path(result["hook_path"])
        file_stat = hook_path.stat()
        # Check owner execute bit.
        assert file_stat.st_mode & stat.S_IXUSR

    def test_install_hook_content_contains_post_rewrite(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        result = run_hook_install(repo_path=repo, force=False)

        hook_path = Path(result["hook_path"])
        content = hook_path.read_text(encoding="utf-8")
        assert "post-rewrite" in content
        assert "arctx git hook post-rewrite" in content

    def test_skip_when_hook_already_exists(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        hook_path = repo / ".git" / "hooks" / "post-rewrite"
        hook_path.write_text("# existing hook\n", encoding="utf-8")

        result = run_hook_install(repo_path=repo, force=False)

        assert result["status"] == "skipped"
        # Content should be unchanged.
        assert hook_path.read_text(encoding="utf-8") == "# existing hook\n"

    def test_force_overwrites_existing_hook(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        hook_path = repo / ".git" / "hooks" / "post-rewrite"
        hook_path.write_text("# existing hook\n", encoding="utf-8")

        result = run_hook_install(repo_path=repo, force=True)

        assert result["status"] == "installed"
        content = hook_path.read_text(encoding="utf-8")
        assert "arctx git hook post-rewrite" in content

    def test_error_when_not_a_git_repo(self, tmp_path):
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()
        result = run_hook_install(repo_path=non_repo, force=False)

        assert result["status"] == "error"

    def test_install_also_creates_post_commit_hook(self, tmp_path):
        """Installing hooks should create both post-rewrite and post-commit."""
        repo = _init_git_repo(tmp_path / "repo")
        result = run_hook_install(repo_path=repo, force=False)

        assert result["status"] == "installed"
        post_commit_path = repo / ".git" / "hooks" / "post-commit"
        assert post_commit_path.exists()
        content = post_commit_path.read_text(encoding="utf-8")
        assert "arctx git hook post-commit" in content

    def test_post_commit_hook_is_executable(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        run_hook_install(repo_path=repo, force=False)

        post_commit_path = repo / ".git" / "hooks" / "post-commit"
        file_stat = post_commit_path.stat()
        assert file_stat.st_mode & stat.S_IXUSR
