"""Integration tests for arctx cherry-pick CLI with a real git repo."""

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


def _git_current_sha(path: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(path), capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


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


class TestCherryPickCLIIntegration:
    def test_cherry_pick_records_payload(self, tmp_path, monkeypatch):
        """Create a commit on a feature branch, cherry-pick to main, verify graph."""
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)

        _init_arctx(repo, tmp_path, run_id="run_cp")

        # Create a feature branch and commit to it.
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=str(repo), capture_output=True, check=True,
        )
        (repo / "feat.txt").write_text("feature content\n")
        subprocess.run(
            ["git", "add", "feat.txt"], cwd=str(repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "add feat.txt"],
            cwd=str(repo), capture_output=True, check=True,
        )
        feature_sha = _git_current_sha(repo)

        # Record the feature commit in arctx (dry_run=False would try to commit again;
        # instead, inject head_commit directly to record the already-made commit).
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_cp")
        handle.ensure_work_session(user_id="alice", work_session_id="ws_feat")
        t_feat = handle.git.commit(
            message="add feat.txt",
            branch="feature",
            user_id="alice",
            work_session_id="ws_feat",
            head_commit=feature_sha,
            dry_run=True,
        )
        store.save_run(handle)
        r_feat = {
            "transition_id": t_feat.transition_id,
            "output_node_id": t_feat.output_node_id,
        }

        # Switch back to main.
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=str(repo), capture_output=True, check=True,
        )

        # Cherry-pick the feature commit to main.
        from arctx_cli.ext.git.cherry_pick import run_cherry_pick_command
        from arctx.ext.git.payloads import CherryPickPayload

        r_cp = run_cherry_pick_command(
            source_sha=feature_sha,
            branch=None,
            run_id="run_cp",
            store_dir=_store_dir(tmp_path),
            user_id="alice",
            work_session_id="ws_main",
        )

        assert "transition_id" in r_cp
        assert r_cp["source_commit"] == feature_sha
        assert r_cp["source_transition"] == r_feat["transition_id"]

        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_cp")
        cp_payloads = handle.run_graph.payloads_for_transition(
            r_cp["transition_id"], payload_type="cherry_pick"
        )
        assert len(cp_payloads) == 1
        assert isinstance(cp_payloads[0], CherryPickPayload)
        assert cp_payloads[0].source_commit == feature_sha

    def test_cherry_pick_cross_repo_none_source_transition(self, tmp_path, monkeypatch):
        """Cherry-pick of an unknown sha → source_transition=None in payload."""
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)

        _init_arctx(repo, tmp_path, run_id="run_cp2")

        # Create a commit that arctx does NOT know about.
        (repo / "unknown.txt").write_text("x\n")
        subprocess.run(
            ["git", "add", "unknown.txt"], cwd=str(repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "bare git commit"],
            cwd=str(repo), capture_output=True, check=True,
        )
        foreign_sha = _git_current_sha(repo)

        # Create another commit to cherry-pick from.
        (repo / "pick_src.txt").write_text("pick\n")
        subprocess.run(
            ["git", "add", "pick_src.txt"], cwd=str(repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "pick source"],
            cwd=str(repo), capture_output=True, check=True,
        )
        pick_sha = _git_current_sha(repo)

        # Go back one commit and cherry-pick.
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            cwd=str(repo), capture_output=True, check=True,
        )

        from arctx_cli.ext.git.cherry_pick import run_cherry_pick_command
        from arctx.ext.git.payloads import CherryPickPayload

        r_cp = run_cherry_pick_command(
            source_sha=pick_sha,
            branch="main",
            run_id="run_cp2",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            work_session_id="ws_cp2",
        )

        assert r_cp["source_transition"] is None
        assert r_cp["source_commit"] == pick_sha
