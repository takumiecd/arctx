"""Integration test for arctx hook post-rewrite.

Simulates what git does when post-rewrite hook fires after amend/rebase:
- Creates a real git repo.
- Runs arctx init + arctx commit (via run_commit_command).
- Directly calls run_hook_post_rewrite with stdin_lines to simulate the hook.
- Verifies that the new GitChangePayload is appended to the correct transition.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from arctx_cli.ext.git.commit import run_commit_command
from arctx_cli.ext.git.hook import run_hook_post_rewrite
from arctx_cli.commands.init import run_init_command
from arctx_cli.context import resolve_store
from arctx.core.schema.work_helpers import AMEND_EVENT, REBASE_EVENT


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
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path), capture_output=True, check=True,
    )
    return path


def _store_dir(tmp_path: Path) -> str:
    return str(tmp_path / "arctx_home" / "runs")


def _init_arctx(repo: Path, tmp_path: Path, run_id: str = "run_pr") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        extensions=["git"],
        no_hooks=True,
    )


class TestHookPostRewriteAmend:
    def test_amend_appends_new_git_change_payload(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path)

        # Make and stage a file.
        (repo / "a.txt").write_text("hello\n")
        subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True, capture_output=True)

        commit_result = run_commit_command(
            message="add a.txt",
            branch="main",
            run_id="run_pr",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws",
        )
        old_sha = commit_result["head_commit"]
        t_id = commit_result["transition_id"]

        # Simulate amend: create a new sha (we just use a fake sha for post-rewrite test).
        new_sha = "amended_" + old_sha[:8]

        result = run_hook_post_rewrite(
            mode="amend",
            run_id="run_pr",
            store_dir=_store_dir(tmp_path),
            stdin_lines=[f"{old_sha} {new_sha}"],
            user_id="user",
            work_session_id="ws",
        )

        assert t_id in result["affected_transitions"]
        assert result["skipped_shas"] == []

        # Verify persistence.
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_pr")
        assert handle.git.current_sha(t_id) == new_sha

    def test_amend_records_amend_event(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path, run_id="run_amend_evt")

        (repo / "b.txt").write_text("b\n")
        subprocess.run(["git", "add", "b.txt"], cwd=str(repo), check=True, capture_output=True)

        commit_result = run_commit_command(
            message="add b.txt",
            branch="main",
            run_id="run_amend_evt",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws",
        )
        old_sha = commit_result["head_commit"]

        run_hook_post_rewrite(
            mode="amend",
            run_id="run_amend_evt",
            store_dir=_store_dir(tmp_path),
            stdin_lines=[f"{old_sha} amended_sha"],
            user_id="user",
            work_session_id="ws",
        )

        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_amend_evt")
        amend_events = [
            e for e in handle.run_graph.work_events if e.event_type == AMEND_EVENT
        ]
        assert len(amend_events) == 1

    def test_unknown_sha_is_skipped(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path, run_id="run_skip")

        result = run_hook_post_rewrite(
            mode="amend",
            run_id="run_skip",
            store_dir=_store_dir(tmp_path),
            stdin_lines=["deadbeef1234 newsha5678"],
            user_id="user",
            work_session_id="ws",
        )

        assert "deadbeef1234" in result["skipped_shas"]
        assert result["affected_transitions"] == []

    def test_empty_stdin_is_noop(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path, run_id="run_empty")

        result = run_hook_post_rewrite(
            mode="amend",
            run_id="run_empty",
            store_dir=_store_dir(tmp_path),
            stdin_lines=[],
            user_id="user",
            work_session_id="ws",
        )

        assert result["affected_transitions"] == []
        assert result["skipped_shas"] == []
        assert result["event_id"] is None


class TestHookPostRewriteRebase:
    def test_rebase_updates_multiple_transitions(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path, run_id="run_rebase")

        # Commit 1.
        (repo / "c1.txt").write_text("c1\n")
        subprocess.run(["git", "add", "c1.txt"], cwd=str(repo), check=True, capture_output=True)
        r1 = run_commit_command(
            message="c1",
            branch="main",
            run_id="run_rebase",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws",
        )

        # Commit 2.
        (repo / "c2.txt").write_text("c2\n")
        subprocess.run(["git", "add", "c2.txt"], cwd=str(repo), check=True, capture_output=True)
        r2 = run_commit_command(
            message="c2",
            branch="main",
            run_id="run_rebase",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws",
        )

        old1, old2 = r1["head_commit"], r2["head_commit"]
        new1, new2 = "rebased_" + old1[:6], "rebased_" + old2[:6]

        result = run_hook_post_rewrite(
            mode="rebase",
            run_id="run_rebase",
            store_dir=_store_dir(tmp_path),
            stdin_lines=[f"{old1} {new1}", f"{old2} {new2}"],
            user_id="user",
            work_session_id="ws",
        )

        assert r1["transition_id"] in result["affected_transitions"]
        assert r2["transition_id"] in result["affected_transitions"]
        assert result["skipped_shas"] == []

        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_rebase")
        assert handle.git.current_sha(r1["transition_id"]) == new1
        assert handle.git.current_sha(r2["transition_id"]) == new2

    def test_rebase_records_rebase_event(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        _init_arctx(repo, tmp_path, run_id="run_rebase_evt")

        (repo / "d.txt").write_text("d\n")
        subprocess.run(["git", "add", "d.txt"], cwd=str(repo), check=True, capture_output=True)
        r = run_commit_command(
            message="d",
            branch="main",
            run_id="run_rebase_evt",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws",
        )

        run_hook_post_rewrite(
            mode="rebase",
            run_id="run_rebase_evt",
            store_dir=_store_dir(tmp_path),
            stdin_lines=[f"{r['head_commit']} rebased_sha"],
            user_id="user",
            work_session_id="ws",
        )

        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_rebase_evt")
        rebase_events = [
            e for e in handle.run_graph.work_events if e.event_type == REBASE_EVENT
        ]
        assert len(rebase_events) == 1
