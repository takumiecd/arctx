"""Integration tests for git worktree attachment.

Covers:
- ``ARCTX_GIT_WORKTREE`` makes ``arctx git commit`` target a linked worktree.
- ``arctx work-session start --worktree`` records the worktree on the
  WorkSession metadata and ``arctx work-session env --worktree`` emits an
  ``export ARCTX_GIT_WORKTREE=...`` line.
- ``arctx git worktree add / list / remove`` round-trip a worktree.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.work_session import (
    run_work_session_env_command,
    run_work_session_start_command,
)
from arctx_cli.context import resolve_store


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _init_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=str(path), capture_output=True, check=True)
    _git(["config", "user.email", "test@example.com"], path)
    _git(["config", "user.name", "Test User"], path)
    (path / "README.md").write_text("hello\n")
    _git(["add", "README.md"], path)
    _git(["commit", "-m", "initial"], path)
    return path


def _store_dir(tmp_path: Path) -> str:
    return str(tmp_path / "arctx_home" / "runs")


def _init_arctx(repo: Path, tmp_path: Path, run_id: str = "run_wt") -> dict:  # noqa: ARG001
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        extensions=["git"],
        no_hooks=True,
    )


class TestArctxGitWorktreeEnv:
    def test_commit_in_linked_worktree_via_env(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path, run_id="run_wt")

        worktree = tmp_path / "wt_a"
        _git(["worktree", "add", "-b", "feature/a", str(worktree)], repo)

        # Edit + stage inside the linked worktree only.
        (worktree / "wt_file.txt").write_text("from worktree A\n")
        _git(["add", "wt_file.txt"], worktree)

        # Primary checkout has no staged work — if ARCTX_GIT_WORKTREE is
        # ignored, the commit subprocess will fail in the primary repo.
        monkeypatch.setenv("ARCTX_GIT_WORKTREE", str(worktree))

        from arctx_cli.ext.git.commit import run_commit_command

        result = run_commit_command(
            message="A: from worktree",
            branch=None,
            run_id="run_wt",
            store_dir=_store_dir(tmp_path),
            user_id="agent-a",
            work_session_id="ws_a",
        )

        assert result["branch"] == "feature/a"

        # The recorded SHA must be the worktree's HEAD, not the primary
        # repo's (those should differ now).
        wt_head = _git(["rev-parse", "HEAD"], worktree)
        primary_head = _git(["rev-parse", "HEAD"], repo)
        assert result["head_commit"] == wt_head
        assert wt_head != primary_head


class TestArctxWorkSessionWorktreeFlag:
    def test_start_records_worktree_metadata(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path, run_id="run_meta")

        worktree = tmp_path / "wt_b"
        _git(["worktree", "add", "-b", "feature/b", str(worktree)], repo)

        result = run_work_session_start_command(
            run_id="run_meta",
            work_session_id="ws_b",
            user_id="agent-b",
            store_dir=_store_dir(tmp_path),
            worktree=str(worktree),
        )

        assert result["worktree"] == str(worktree.resolve())

        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_meta")
        ws = handle.run_graph.work_sessions["ws_b"]
        assert ws.metadata["worktree"]["path"] == str(worktree.resolve())
        assert ws.metadata["worktree"]["branch"] == "feature/b"

    def test_env_emits_export_line(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path, run_id="run_env")
        worktree = tmp_path / "wt_c"
        _git(["worktree", "add", "-b", "feature/c", str(worktree)], repo)

        result = run_work_session_env_command(
            run_id="run_env",
            work_session_id=None,
            create_new=True,
            user_id="agent-c",
            store_dir=_store_dir(tmp_path),
            worktree=str(worktree),
        )

        from arctx_cli.commands.work_session import _env_exports

        exports = _env_exports(result)
        # Should include ARCTX_GIT_WORKTREE export with the resolved path.
        assert "export ARCTX_GIT_WORKTREE=" in exports
        # Round-trip the shell-quoted value back into a path string.
        wt_line = [
            line for line in exports.splitlines() if line.startswith("export ARCTX_GIT_WORKTREE=")
        ][0]
        _, _, value = wt_line.partition("=")
        # shlex.split treats the value as shell tokens; should yield exactly one.
        parsed = shlex.split(value)
        assert parsed == [str(worktree.resolve())]


class TestArctxGitWorktreeCLI:
    def test_add_list_remove(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path, run_id="run_cli")

        from arctx_cli.ext.git.worktree import cli_worktree

        target = tmp_path / "wt_d"

        class _A:
            pass

        a = _A()
        a.worktree_command = "add"
        a.path = str(target)
        a.branch = None
        a.base = None
        a.existing_branch = False
        a.store_dir = _store_dir(tmp_path)
        rc = cli_worktree(a)
        assert rc == 0
        assert (target / ".git").exists()

        b = _A()
        b.worktree_command = "list"
        b.store_dir = _store_dir(tmp_path)
        rc = cli_worktree(b)
        assert rc == 0

        c = _A()
        c.worktree_command = "remove"
        c.path = str(target)
        c.force = True
        c.store_dir = _store_dir(tmp_path)
        rc = cli_worktree(c)
        assert rc == 0
        assert not target.exists()
