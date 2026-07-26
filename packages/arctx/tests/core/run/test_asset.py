"""Tests for git-native assets: RunHandle.attach_asset and arctx.core.gitref.

Assets are ``(commit, path)`` references into the repository enclosing the run,
so these tests build real temporary git repositories (subprocess git, as the
git-extension tests already do).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import arctx as arctx
from arctx.core.gitref import (
    GitRefError,
    MissingCommit,
    MissingPath,
    guess_content_type,
    head_commit,
    list_tree,
    normalize_repo_path,
    read_blob,
    unpushed_warning,
)
from arctx.core.schema.payloads import AssetPayload
from arctx.core.schema.requirements import Requirement
from arctx.storage.jsonl import JsonlRunStore


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], path)
    _run(["git", "config", "user.email", "test@example.com"], path)
    _run(["git", "config", "user.name", "Test User"], path)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    (path / "bench").mkdir()
    (path / "bench" / "result.txt").write_text("score=0.9\n", encoding="utf-8")
    (path / "bench" / "plot.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-qm", "initial"], path)
    return path


def _handle():
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return arctx.init(req, run_id="run_asset")


@pytest.fixture
def repo(tmp_path):
    return _init_repo(tmp_path / "repo")


class TestAttachAsset:
    def test_defaults_to_head_and_records_full_sha(self, repo):
        handle = _handle()
        result = handle.attach_asset(
            handle.root_node_id, "bench/result.txt", repo_root=repo
        )

        assert isinstance(result.payload, AssetPayload)
        assert result.payload.payload_type == "asset"
        assert result.payload.target_kind == "node"
        assert result.payload.path == "bench/result.txt"
        assert result.payload.commit == head_commit(repo)
        assert len(result.payload.commit) == 40
        assert result.kind == "blob"
        assert result.payload.payload_id in handle.run_graph.payloads

    def test_explicit_commit_is_resolved_to_a_full_sha(self, repo):
        first = head_commit(repo)
        (repo / "bench" / "result.txt").write_text("score=0.95\n", encoding="utf-8")
        _run(["git", "commit", "-aqm", "second"], repo)

        handle = _handle()
        result = handle.attach_asset(
            handle.root_node_id, "bench/result.txt", commit=first[:8], repo_root=repo
        )
        assert result.payload.commit == first
        assert read_blob(repo, result.payload.commit, result.payload.path) == b"score=0.9\n"

    def test_directory_path_is_allowed(self, repo):
        handle = _handle()
        result = handle.attach_asset(handle.root_node_id, "bench", repo_root=repo)
        assert result.kind == "tree"
        names = [e.name for e in list_tree(repo, result.payload.commit, "bench")]
        assert names == ["plot.png", "result.txt"]

    def test_step_target_is_supported(self, repo):
        from arctx.core.schema.payloads import StepPayload

        handle = _handle()
        step = handle.add_step(
            [handle.root_node_id],
            StepPayload(payload_id="pending", target_id="pending", type="try"),
        )
        result = handle.attach_asset(step.step_id, "README.md", repo_root=repo)
        assert result.payload.target_kind == "step"
        assert result.payload.target_id == step.step_id

    def test_nonexistent_path_is_rejected(self, repo):
        handle = _handle()
        with pytest.raises(MissingPath):
            handle.attach_asset(handle.root_node_id, "bench/nope.txt", repo_root=repo)

    def test_uncommitted_file_is_rejected(self, repo):
        (repo / "draft.txt").write_text("not committed\n", encoding="utf-8")
        handle = _handle()
        with pytest.raises(MissingPath):
            handle.attach_asset(handle.root_node_id, "draft.txt", repo_root=repo)

    def test_unknown_commit_is_rejected(self, repo):
        handle = _handle()
        with pytest.raises(MissingCommit):
            handle.attach_asset(
                handle.root_node_id, "README.md", commit="0" * 40, repo_root=repo
            )

    def test_unknown_target_is_rejected(self, repo):
        handle = _handle()
        with pytest.raises(KeyError):
            handle.attach_asset("n_nope", "README.md", repo_root=repo)

    def test_outside_a_git_repo_fails_clearly(self, tmp_path, monkeypatch):
        plain = tmp_path / "plain"
        plain.mkdir()
        monkeypatch.chdir(plain)
        monkeypatch.setattr(
            "arctx.core.gitref.find_repo_root",
            lambda start=None: (_ for _ in ()).throw(RuntimeError("no .git")),
        )
        handle = _handle()
        with pytest.raises(GitRefError, match="not inside a git repository"):
            handle.attach_asset(handle.root_node_id, "README.md")

    def test_cwd_relative_path_is_normalized(self, repo, monkeypatch):
        monkeypatch.chdir(repo / "bench")
        handle = _handle()
        result = handle.attach_asset(handle.root_node_id, "result.txt", repo_root=repo)
        assert result.payload.path == "bench/result.txt"

    def test_records_a_work_event(self, repo):
        handle = _handle()
        handle.attach_asset(
            handle.root_node_id, "README.md", repo_root=repo,
            user_id="alice", lane_id="lane_1", title="readme",
        )
        events = [e for e in handle.run_graph.work_events if e.event_type == "asset_attached"]
        assert len(events) == 1
        assert events[0].summary == "readme"


class TestPushWarning:
    def test_warns_when_no_remote(self, repo):
        handle = _handle()
        result = handle.attach_asset(handle.root_node_id, "README.md", repo_root=repo)
        assert result.warning is not None
        assert "no remote" in result.warning

    def test_warns_when_commit_is_not_pushed(self, tmp_path, repo):
        bare = tmp_path / "origin.git"
        _run(["git", "init", "-q", "--bare", str(bare)], tmp_path)
        _run(["git", "remote", "add", "origin", str(bare)], repo)
        _run(["git", "push", "-q", "origin", "HEAD"], repo)
        _run(["git", "fetch", "-q", "origin"], repo)

        # A fresh, unpushed commit.
        (repo / "later.txt").write_text("later\n", encoding="utf-8")
        _run(["git", "add", "later.txt"], repo)
        _run(["git", "commit", "-qm", "later"], repo)

        handle = _handle()
        unpushed = handle.attach_asset(handle.root_node_id, "later.txt", repo_root=repo)
        assert unpushed.warning is not None
        assert "not contained in any remote-tracking branch" in unpushed.warning

    def test_no_warning_when_commit_is_on_a_remote(self, tmp_path, repo):
        bare = tmp_path / "origin.git"
        _run(["git", "init", "-q", "--bare", str(bare)], tmp_path)
        _run(["git", "remote", "add", "origin", str(bare)], repo)
        _run(["git", "push", "-q", "origin", "HEAD"], repo)
        _run(["git", "fetch", "-q", "origin"], repo)

        handle = _handle()
        result = handle.attach_asset(handle.root_node_id, "README.md", repo_root=repo)
        assert result.warning is None
        assert unpushed_warning(repo, head_commit(repo)) is None


class TestGitRefHelpers:
    def test_normalize_rejects_escaping_paths(self):
        with pytest.raises(GitRefError):
            normalize_repo_path("../secrets")

    def test_normalize_root(self):
        assert normalize_repo_path(".") == ""
        assert normalize_repo_path("./bench/") == "bench"

    def test_content_type_guess(self):
        assert guess_content_type("bench/plot.png") == "image/png"
        assert guess_content_type("notes.md").startswith("text/markdown")
        assert guess_content_type("blob.bin") == "application/octet-stream"

    def test_read_blob_is_binary_safe(self, repo):
        data = read_blob(repo, head_commit(repo), "bench/plot.png")
        assert data == b"\x89PNG\r\n\x1a\n\x00\xff"


class TestAssetRoundTrip:
    def test_jsonl_round_trip(self, tmp_path, repo):
        handle = _handle()
        result = handle.attach_asset(
            handle.root_node_id, "bench", repo_root=repo, title="bench dir"
        )
        store = JsonlRunStore(str(tmp_path / "runs"))
        store.save_run(handle)

        loaded = store.load_run(handle.run_id)
        reloaded = loaded.run_graph.payloads[result.payload.payload_id]
        assert isinstance(reloaded, AssetPayload)
        assert reloaded.payload_type == "asset"
        assert reloaded.commit == result.payload.commit
        assert reloaded.path == "bench"
        assert reloaded.title == "bench dir"
        assert reloaded.target_kind == "node"

    def test_export_json_includes_assets(self, repo):
        from arctx.core.run.export import ExportOptions, json_document

        handle = _handle()
        result = handle.attach_asset(handle.root_node_id, "README.md", repo_root=repo)
        doc = json_document(handle, ExportOptions())
        assets = [p for p in doc["payloads"] if p["payload_type"] == "asset"]
        assert len(assets) == 1
        assert assets[0]["payload_id"] == result.payload.payload_id
        assert assets[0]["path"] == "README.md"
