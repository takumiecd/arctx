"""Integration tests for stag commit CLI with a real git repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from stag_cli.commands.init import run_init_command
from stag_cli.context import resolve_store


def _init_git_repo(path: Path) -> Path:
    """Create a real git repo with an initial commit."""
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
    # Create initial commit so HEAD exists.
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path), capture_output=True, check=True,
    )
    return path


def _stag_home(tmp_path: Path) -> Path:
    return tmp_path / "stag_home"


def _store_dir(tmp_path: Path) -> str:
    return str(_stag_home(tmp_path) / "runs")


def _init_stag(repo: Path, tmp_path: Path, run_id: str = "run_test") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        extensions=["git"],
    )


class TestCommitCLIIntegration:
    def test_stag_commit_records_transition(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
        monkeypatch.setenv("STAG_WORK_SESSION_ID", "ws_test")
        monkeypatch.setenv("STAG_USER_ID", "alice")
        monkeypatch.chdir(repo)

        _init_stag(repo, tmp_path, run_id="run_ci")

        # Make a file change and stage it.
        (repo / "foo.txt").write_text("bar\n")
        subprocess.run(["git", "add", "foo.txt"], cwd=str(repo), check=True, capture_output=True)

        from stag_cli.ext.git.commit import run_commit_command

        result = run_commit_command(
            message="add foo.txt",
            branch=None,
            run_id="run_ci",
            store_dir=_store_dir(tmp_path),
            user_id="alice",
            work_session_id="ws_test",
        )

        assert "transition_id" in result
        assert "output_node_id" in result
        assert result["head_commit"] != ""

    def test_commit_advances_branch_tip(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
        monkeypatch.chdir(repo)

        _init_stag(repo, tmp_path, run_id="run_bt")

        (repo / "a.txt").write_text("a\n")
        subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True, capture_output=True)

        from stag_cli.ext.git.commit import run_commit_command
        from stag_api.core.schema.work_helpers import latest_branch_tip

        result = run_commit_command(
            message="add a.txt",
            branch="main",
            run_id="run_bt",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws_1",
        )

        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_bt")

        tip_event = latest_branch_tip(handle.run_graph, "main")
        assert tip_event is not None
        assert tip_event.data["tip_node_id"] == result["output_node_id"]

    def test_two_commits_form_chain(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
        monkeypatch.chdir(repo)

        _init_stag(repo, tmp_path, run_id="run_chain")

        from stag_cli.ext.git.commit import run_commit_command

        (repo / "c1.txt").write_text("c1\n")
        subprocess.run(["git", "add", "c1.txt"], cwd=str(repo), check=True, capture_output=True)
        r1 = run_commit_command(
            message="first",
            branch="main",
            run_id="run_chain",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws_x",
        )

        (repo / "c2.txt").write_text("c2\n")
        subprocess.run(["git", "add", "c2.txt"], cwd=str(repo), check=True, capture_output=True)
        r2 = run_commit_command(
            message="second",
            branch="main",
            run_id="run_chain",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws_x",
        )

        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_chain")

        t2 = handle.run_graph.transitions[r2["transition_id"]]
        assert r1["output_node_id"] in t2.input_node_ids
