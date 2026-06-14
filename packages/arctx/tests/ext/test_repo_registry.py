"""Tests for the git extension repo registry (the repo 対応表).

Covers URL normalization, registry queries, repo_id resolution against real
temporary git repos, and (repo_id, branch) tip keying for two repos that share
a branch name in one run.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import arctx as arctx
from arctx.core.schema.requirements import Requirement
from arctx.ext import attach_extensions
from arctx.ext.git.payloads import BranchPayload, GitChangePayload, RepoPayload
from arctx.ext.git.registry import (
    list_repos,
    normalize_remote_url,
    read_repo_marker,
    repo_by_canonical,
    resolve_repo_id,
    slug_from_canonical,
)


def _make_handle(run_id: str = "run_test"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return attach_extensions(arctx.init(req, run_id=run_id), ["git"])


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(path: Path, *, remote: str | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], path)
    _git(["config", "user.email", "t@example.com"], path)
    _git(["config", "user.name", "t"], path)
    _git(["checkout", "-q", "-b", "main"], path)
    (path / "f.txt").write_text("hi\n")
    _git(["add", "."], path)
    _git(["commit", "-q", "-m", "init"], path)
    if remote is not None:
        _git(["remote", "add", "origin", remote], path)


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------


class TestNormalizeRemoteUrl:
    def test_ssh_and_https_match(self):
        ssh = normalize_remote_url("git@github.com:takumiecd/arctx.git")
        https = normalize_remote_url("https://github.com/takumiecd/arctx.git")
        assert ssh == https == "github.com/takumiecd/arctx"

    def test_ssh_scheme_form(self):
        assert (
            normalize_remote_url("ssh://git@github.com/takumiecd/arctx")
            == "github.com/takumiecd/arctx"
        )

    def test_trailing_slash_and_case(self):
        assert (
            normalize_remote_url("https://GitHub.com/Takumiecd/Arctx/")
            == "github.com/takumiecd/arctx"
        )

    def test_unrecognized_returns_none(self):
        assert normalize_remote_url("") is None
        assert normalize_remote_url("not a url") is None

    def test_slug_from_canonical(self):
        assert slug_from_canonical("github.com/takumiecd/arctx") == "takumiecd/arctx"
        assert slug_from_canonical(None) is None


# ---------------------------------------------------------------------------
# Resolution against real temp git repos
# ---------------------------------------------------------------------------


class TestResolveRepoId:
    def test_registers_new_repo_with_remote(self, tmp_path):
        repo = tmp_path / "r1"
        _init_repo(repo, remote="git@github.com:takumiecd/arctx.git")
        handle = _make_handle()

        repo_id = resolve_repo_id(handle, repo)

        assert repo_id.startswith("repo_")
        repos = list_repos(handle.run_graph)
        assert len(repos) == 1
        entry = repos[0]
        assert entry.repo_id == repo_id
        assert entry.canonical == "github.com/takumiecd/arctx"
        assert entry.slug == "takumiecd/arctx"
        assert entry.local_path == str(repo.resolve())
        # marker written so next resolution is direct
        assert read_repo_marker(repo) == repo_id

    def test_second_call_is_idempotent(self, tmp_path):
        repo = tmp_path / "r1"
        _init_repo(repo, remote="git@github.com:takumiecd/arctx.git")
        handle = _make_handle()

        first = resolve_repo_id(handle, repo)
        second = resolve_repo_id(handle, repo)

        assert first == second
        assert len(list_repos(handle.run_graph)) == 1

    def test_ssh_then_https_clone_match_same_repo(self, tmp_path):
        """Two checkouts of the same upstream (ssh vs https) resolve to one id."""
        repo_ssh = tmp_path / "ssh_clone"
        repo_https = tmp_path / "https_clone"
        _init_repo(repo_ssh, remote="git@github.com:takumiecd/arctx.git")
        _init_repo(repo_https, remote="https://github.com/takumiecd/arctx.git")
        handle = _make_handle()

        id_ssh = resolve_repo_id(handle, repo_ssh)
        id_https = resolve_repo_id(handle, repo_https)

        assert id_ssh == id_https
        assert len(list_repos(handle.run_graph)) == 1

    def test_local_repo_without_remote(self, tmp_path):
        repo = tmp_path / "local_only"
        _init_repo(repo, remote=None)
        handle = _make_handle()

        repo_id = resolve_repo_id(handle, repo)

        entry = list_repos(handle.run_graph)[0]
        assert entry.repo_id == repo_id
        assert entry.canonical is None
        assert entry.remotes == ()

    def test_two_distinct_repos_get_distinct_ids(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        _init_repo(a, remote="git@github.com:takumiecd/alpha.git")
        _init_repo(b, remote="git@github.com:takumiecd/beta.git")
        handle = _make_handle()

        id_a = resolve_repo_id(handle, a)
        id_b = resolve_repo_id(handle, b)

        assert id_a != id_b
        assert len(list_repos(handle.run_graph)) == 2
        assert repo_by_canonical(handle.run_graph, "github.com/takumiecd/alpha").repo_id == id_a


# ---------------------------------------------------------------------------
# (repo_id, branch) tip keying — two 'main' branches do not collide
# ---------------------------------------------------------------------------


class TestMultiRepoTipKeying:
    def test_same_branch_name_two_repos_no_conflict(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        _init_repo(a, remote="git@github.com:takumiecd/alpha.git")
        _init_repo(b, remote="git@github.com:takumiecd/beta.git")
        handle = _make_handle()
        handle.ensure_work_session(user_id="u", work_session_id="ws")

        # Stage a real change, then commit on repo A 'main'.
        (a / "f.txt").write_text("a change\n")
        _git(["add", "."], a)
        t_a = handle.git.commit(
            message="a1", repo_path=a, user_id="u", work_session_id="ws"
        )
        # Committing on repo B 'main' from the run root must NOT raise a
        # ParallelSessionConflict despite the shared branch name, because the
        # tip is keyed by (repo_id, branch).
        (b / "f.txt").write_text("b change\n")
        _git(["add", "."], b)
        t_b = handle.git.commit(
            message="b1", repo_path=b, user_id="u", work_session_id="ws"
        )

        a_git = handle.run_graph.payloads_for_step(
            t_a.step_id, payload_type="git_change"
        )[0]
        b_git = handle.run_graph.payloads_for_step(
            t_b.step_id, payload_type="git_change"
        )[0]
        assert isinstance(a_git, GitChangePayload)
        assert a_git.repo_id != ""
        assert b_git.repo_id != ""
        assert a_git.repo_id != b_git.repo_id
