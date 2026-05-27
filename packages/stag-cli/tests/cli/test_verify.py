"""Integration tests for stag verify CLI.

Two flavours:
1. Real git repo tests: stag init → stag commit → stag verify (actual git calls).
2. Mock-based tests: simulate non_descendant / dead_sha cases without a real git history.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from stag_cli.commands.init import run_init_command
from stag_cli.ext.git.verify import run_verify_command
from stag_cli.context import resolve_store


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> Path:
    """Create a minimal git repo with one initial commit."""
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


def _stag_home(tmp_path: Path) -> Path:
    return tmp_path / "stag_home"


def _store_dir(tmp_path: Path) -> str:
    return str(_stag_home(tmp_path) / "runs")


def _init_stag(tmp_path: Path, run_id: str = "run_test") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        extensions=["git"],
        no_hooks=True,
    )


def _get_head_sha(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _git_commit_file(repo: Path, filename: str, message: str) -> str:
    """Write a file, stage, commit, and return the new HEAD sha."""
    (repo / filename).write_text(f"{message}\n")
    subprocess.run(["git", "add", filename], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(repo), capture_output=True, check=True,
    )
    return _get_head_sha(repo)


# ---------------------------------------------------------------------------
# Real git integration tests
# ---------------------------------------------------------------------------


class TestVerifyCLIRealGit:
    def test_linear_chain_no_violations(self, tmp_path, monkeypatch):
        """Linear chain of two real commits → verify passes with 0 violations."""
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
        monkeypatch.setenv("STAG_WORK_SESSION_ID", "ws_v")
        monkeypatch.setenv("STAG_USER_ID", "alice")
        monkeypatch.chdir(repo)

        _init_stag(tmp_path, run_id="run_v")
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_v")
        handle.ensure_work_session(user_id="alice", work_session_id="ws_v")

        sha1 = _git_commit_file(repo, "f1.txt", "first")
        t1 = handle.git.commit(
            message="first",
            branch="main",
            user_id="alice",
            work_session_id="ws_v",
            head_commit=sha1,
            dry_run=True,  # git commit already done above
        )

        sha2 = _git_commit_file(repo, "f2.txt", "second")
        t2 = handle.git.commit(
            message="second",
            branch="main",
            user_id="alice",
            work_session_id="ws_v",
            head_commit=sha2,
            dry_run=True,
        )

        store.save_run(handle)

        result = run_verify_command(
            run_id="run_v",
            store_dir=_store_dir(tmp_path),
            repo_path=repo,
        )

        assert result["summary"]["violations"] == 0
        assert result["violations"] == []

    def test_amend_sha_update_no_violations(self, tmp_path, monkeypatch):
        """After amend + sha update via adopt_rewrite, verify still passes."""
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
        monkeypatch.setenv("STAG_WORK_SESSION_ID", "ws_a")
        monkeypatch.setenv("STAG_USER_ID", "alice")
        monkeypatch.chdir(repo)

        _init_stag(tmp_path, run_id="run_a")
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_a")
        handle.ensure_work_session(user_id="alice", work_session_id="ws_a")

        sha1 = _git_commit_file(repo, "f1.txt", "first")
        t1 = handle.git.commit(
            message="first",
            branch="main",
            user_id="alice",
            work_session_id="ws_a",
            head_commit=sha1,
            dry_run=True,
        )

        # Amend the last commit.
        (repo / "f1.txt").write_text("amended\n")
        subprocess.run(
            ["git", "commit", "--amend", "--no-edit"],
            cwd=str(repo), capture_output=True, check=True,
        )
        new_sha = _get_head_sha(repo)

        # Update stag record via adopt_rewrite (amend mode, no onto needed).
        handle.git.adopt_rewrite(
            sha_map={sha1: new_sha},
            onto=new_sha,
            mode="amend",
            user_id="alice",
            work_session_id="ws_a",
        )
        store.save_run(handle)

        result = run_verify_command(
            run_id="run_a",
            store_dir=_store_dir(tmp_path),
            repo_path=repo,
        )

        assert result["summary"]["violations"] == 0

    def test_non_descendant_detected_real_git(self, tmp_path, monkeypatch):
        """Simulate a non-descendant situation using two independent git commits."""
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("STAG_HOME", str(_stag_home(tmp_path)))
        monkeypatch.setenv("STAG_WORK_SESSION_ID", "ws_nd")
        monkeypatch.setenv("STAG_USER_ID", "alice")
        monkeypatch.chdir(repo)

        _init_stag(tmp_path, run_id="run_nd")
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_nd")
        handle.ensure_work_session(user_id="alice", work_session_id="ws_nd")

        # sha_A = first commit on main.
        sha_A = _git_commit_file(repo, "f1.txt", "commit A")

        # Create an orphan branch with an independent commit (no common parent = branch from initial).
        subprocess.run(
            ["git", "checkout", "--orphan", "orphan"],
            cwd=str(repo), capture_output=True, check=True,
        )
        subprocess.run(["git", "rm", "-rf", "."], cwd=str(repo), capture_output=True)
        (repo / "other.txt").write_text("other\n")
        subprocess.run(["git", "add", "other.txt"], cwd=str(repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "orphan commit"],
            cwd=str(repo), capture_output=True, check=True,
        )
        sha_B = _get_head_sha(repo)

        # Switch back to main.
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=str(repo), capture_output=True, check=True,
        )

        # Record t1 with sha_A, then t2 with sha_B (sha_B is NOT a descendant of sha_A).
        t1 = handle.git.commit(
            message="commit A",
            branch="main",
            user_id="alice",
            work_session_id="ws_nd",
            head_commit=sha_A,
            dry_run=True,
        )
        t2 = handle.git.commit(
            message="commit B (wrong sha)",
            branch="main",
            user_id="alice",
            work_session_id="ws_nd",
            head_commit=sha_B,
            dry_run=True,
        )
        store.save_run(handle)

        result = run_verify_command(
            run_id="run_nd",
            store_dir=_store_dir(tmp_path),
            repo_path=repo,
        )

        assert result["summary"]["violations"] >= 1
        kinds = [v["kind"] for v in result["violations"]]
        assert "non_descendant" in kinds


# ---------------------------------------------------------------------------
# Mock-based CLI tests (no real git needed)
# ---------------------------------------------------------------------------


class TestVerifyCLIMocked:
    def _setup_run(self, tmp_path, run_id: str = "run_m"):
        """Create a stag run with a two-commit chain in a temp store."""
        _init_stag(tmp_path, run_id=run_id)
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run(run_id)
        handle.ensure_work_session(user_id="alice", work_session_id="ws_m")
        for i, sha in enumerate(["sha_A", "sha_B"]):
            handle.git.commit(
                message=f"commit {i + 1}",
                branch="main",
                user_id="alice",
                work_session_id="ws_m",
                head_commit=sha,
                dry_run=True,
            )
        store.save_run(handle)
        return store

    def test_no_violations_returns_0_count(self, tmp_path):
        """With git mocked to always succeed, verify returns 0 violations."""
        self._setup_run(tmp_path, run_id="run_ok")

        def _git_ok(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=_git_ok):
            result = run_verify_command(
                run_id="run_ok",
                store_dir=_store_dir(tmp_path),
            )

        assert result["summary"]["violations"] == 0
        assert result["violations"] == []

    def test_non_descendant_returns_1_violation(self, tmp_path):
        """With merge-base returning 1 (not ancestor), we get a non_descendant."""
        self._setup_run(tmp_path, run_id="run_fail")

        def _git_mock(cmd, **kwargs):
            m = MagicMock()
            if "merge-base" in cmd and "--is-ancestor" in cmd:
                m.returncode = 1
            else:
                m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=_git_mock):
            result = run_verify_command(
                run_id="run_fail",
                store_dir=_store_dir(tmp_path),
            )

        assert result["summary"]["violations"] >= 1
        kinds = {v["kind"] for v in result["violations"]}
        assert "non_descendant" in kinds

    def test_summary_by_kind_populated(self, tmp_path):
        """summary.by_kind is populated correctly."""
        self._setup_run(tmp_path, run_id="run_bk")

        def _git_mock(cmd, **kwargs):
            m = MagicMock()
            if "merge-base" in cmd and "--is-ancestor" in cmd:
                m.returncode = 1
            else:
                m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=_git_mock):
            result = run_verify_command(
                run_id="run_bk",
                store_dir=_store_dir(tmp_path),
            )

        assert "non_descendant" in result["summary"]["by_kind"]
        assert result["summary"]["by_kind"]["non_descendant"] >= 1

    def test_checked_count_matches_active_transitions(self, tmp_path):
        """summary.checked equals the number of non-cut transitions."""
        self._setup_run(tmp_path, run_id="run_cnt")

        def _git_ok(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=_git_ok):
            result = run_verify_command(
                run_id="run_cnt",
                store_dir=_store_dir(tmp_path),
            )

        # Two commits → 2 active transitions.
        assert result["summary"]["checked"] == 2
