"""Tests for arctx branch list/show CLI commands."""

from __future__ import annotations

import subprocess
from pathlib import Path

from arctx_cli.commands.init import run_init_command
from arctx_cli.ext.git.branch import run_branch_list_command, run_branch_show_command
from arctx_cli.ext.git.commit import run_commit_command


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


def _arctx_home(tmp_path: Path) -> Path:
    return tmp_path / "arctx_home"


def _store_dir(tmp_path: Path) -> str:
    return str(_arctx_home(tmp_path) / "runs")


class TestBranchListCommand:
    def test_empty_when_no_commits(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
        monkeypatch.chdir(repo)

        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_bl",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
        )

        result = run_branch_list_command(run_id="run_bl", store_dir=_store_dir(tmp_path))
        assert result == []

    def test_lists_branch_after_commit(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
        monkeypatch.chdir(repo)

        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_bl2",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
        )

        (repo / "f.txt").write_text("f\n")
        subprocess.run(["git", "add", "f.txt"], cwd=str(repo), check=True, capture_output=True)
        run_commit_command(
            message="commit on main",
            branch="main",
            run_id="run_bl2",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            lane_id="ws_1",
        )

        result = run_branch_list_command(run_id="run_bl2", store_dir=_store_dir(tmp_path))
        branches = [r["branch"] for r in result]
        assert "main" in branches

    def test_lists_multiple_branches(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
        monkeypatch.chdir(repo)

        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_multi",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
        )

        (repo / "m.txt").write_text("m\n")
        subprocess.run(["git", "add", "m.txt"], cwd=str(repo), check=True, capture_output=True)
        run_commit_command(
            message="main commit",
            branch="main",
            run_id="run_multi",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            lane_id="ws_m",
        )

        (repo / "d.txt").write_text("d\n")
        subprocess.run(["git", "add", "d.txt"], cwd=str(repo), check=True, capture_output=True)
        run_commit_command(
            message="dev commit",
            branch="dev",
            run_id="run_multi",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            lane_id="ws_d",
        )

        result = run_branch_list_command(run_id="run_multi", store_dir=_store_dir(tmp_path))
        branches = {r["branch"] for r in result}
        assert "main" in branches
        assert "dev" in branches


class TestBranchShowCommand:
    def test_unknown_branch_returns_none_tip(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
        monkeypatch.chdir(repo)

        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_bs",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
        )

        result = run_branch_show_command(
            name="nonexistent", run_id="run_bs", store_dir=_store_dir(tmp_path)
        )
        assert result["branch"] == "nonexistent"
        assert result["tip_node_id"] is None
        assert result["members_count"] == 0

    def test_show_after_commit(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
        monkeypatch.chdir(repo)

        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_bs2",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
        )

        (repo / "x.txt").write_text("x\n")
        subprocess.run(["git", "add", "x.txt"], cwd=str(repo), check=True, capture_output=True)
        commit_result = run_commit_command(
            message="commit for show test",
            branch="main",
            run_id="run_bs2",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            lane_id="ws_1",
        )

        result = run_branch_show_command(
            name="main", run_id="run_bs2", store_dir=_store_dir(tmp_path)
        )
        assert result["tip_node_id"] == commit_result["output_node_id"]
        assert result["members_count"] >= 1
        assert len(result["steps"]) >= 1

    def test_steps_include_branch_payload_info(self, tmp_path, monkeypatch):
        repo = _init_git_repo(tmp_path / "repo")
        monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
        monkeypatch.chdir(repo)

        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_bs3",
            store_dir=_store_dir(tmp_path),
            extensions=["git"],
        )

        (repo / "y.txt").write_text("y\n")
        subprocess.run(["git", "add", "y.txt"], cwd=str(repo), check=True, capture_output=True)
        commit_result = run_commit_command(
            message="commit for branch info",
            branch="main",
            run_id="run_bs3",
            store_dir=_store_dir(tmp_path),
            user_id="user",
            lane_id="ws_1",
        )

        result = run_branch_show_command(
            name="main", run_id="run_bs3", store_dir=_store_dir(tmp_path)
        )
        t_ids = [t["step_id"] for t in result["steps"]]
        assert commit_result["step_id"] in t_ids
