"""Integration tests for arctx revert CLI with a real git repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from arctx_cli.commands.init import run_init_command
from arctx_cli.context import resolve_store


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
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path), capture_output=True, check=True,
    )
    return path


def _store_dir(tmp_path: Path) -> str:
    return str(tmp_path / "arctx_home" / "runs")


def _init_arctx(repo: Path, tmp_path: Path, run_id: str = "run_test") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        extensions=["git"],
        no_hooks=True,
    )


class TestRevertCLIIntegration:
    def test_revert_records_revert_payload(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)

        _init_arctx(repo, tmp_path, run_id="run_rv")

        # Make a commit and record it in arctx.
        (repo / "file.txt").write_text("content\n")
        subprocess.run(["git", "add", "file.txt"], cwd=str(repo), check=True, capture_output=True)

        from arctx_cli.ext.git.commit import run_commit_command
        from arctx_cli.ext.git.revert import run_revert_command
        from arctx.ext.git.payloads import RevertPayload

        r1 = run_commit_command(
            message="add file.txt",
            branch="main",
            run_id="run_rv",
            store_dir=_store_dir(tmp_path),
            user_id="alice",
            work_session_id="ws_rv",
        )

        orig_sha = r1["head_commit"]
        orig_t_id = r1["step_id"]

        # Now revert via arctx.
        r2 = run_revert_command(
            target_sha=orig_sha,
            target_step=None,
            message=None,
            branch=None,
            run_id="run_rv",
            store_dir=_store_dir(tmp_path),
            user_id="alice",
            work_session_id="ws_rv",
        )

        assert "step_id" in r2
        assert r2["reverted_commit"] == orig_sha
        assert r2["reverted_step"] == orig_t_id

        # Load and verify the graph.
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_rv")

        revert_payloads = handle.run_graph.payloads_for_step(
            r2["step_id"], payload_type="revert"
        )
        assert len(revert_payloads) == 1
        assert isinstance(revert_payloads[0], RevertPayload)

    def test_revert_original_step_untouched(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)

        _init_arctx(repo, tmp_path, run_id="run_rv2")

        (repo / "a.txt").write_text("a\n")
        subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True, capture_output=True)

        from arctx_cli.ext.git.commit import run_commit_command
        from arctx_cli.ext.git.revert import run_revert_command

        r1 = run_commit_command(
            message="add a.txt",
            branch="main",
            run_id="run_rv2",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws_rv2",
        )

        store = resolve_store(_store_dir(tmp_path))
        handle_before = store.load_run("run_rv2")
        orig_payloads = list(
            handle_before.run_graph.payloads_by_step.get(r1["step_id"], [])
        )

        run_revert_command(
            target_sha=r1["head_commit"],
            target_step=None,
            message=None,
            branch=None,
            run_id="run_rv2",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws_rv2",
        )

        handle_after = store.load_run("run_rv2")
        after_payloads = list(
            handle_after.run_graph.payloads_by_step.get(r1["step_id"], [])
        )
        assert orig_payloads == after_payloads

    def test_revert_graph_forms_chain(self, tmp_path, monkeypatch):
        """Revert step's input should be the commit step's output."""
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)

        _init_arctx(repo, tmp_path, run_id="run_rv3")

        (repo / "b.txt").write_text("b\n")
        subprocess.run(["git", "add", "b.txt"], cwd=str(repo), check=True, capture_output=True)

        from arctx_cli.ext.git.commit import run_commit_command
        from arctx_cli.ext.git.revert import run_revert_command

        r1 = run_commit_command(
            message="add b.txt",
            branch="main",
            run_id="run_rv3",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws_rv3",
        )

        r2 = run_revert_command(
            target_sha=r1["head_commit"],
            target_step=None,
            message=None,
            branch=None,
            run_id="run_rv3",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws_rv3",
        )

        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_rv3")
        t2 = handle.run_graph.steps[r2["step_id"]]
        assert r1["output_node_id"] in t2.input_node_ids
