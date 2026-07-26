"""Tests for the serve layer's asset read path (socket-free, via ``dispatch``).

Assets resolve through git at request time, so the run store is placed inside a
real temporary repository — exactly the git-native layout.
"""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import pytest
from arctx.core.schema.payloads import AssetPayload
from arctx.serve.api import dispatch
from arctx.session import resolve_store

from arctx_cli.commands.init import run_init_command


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=True)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], path)
    _run(["git", "config", "user.email", "test@example.com"], path)
    _run(["git", "config", "user.name", "Test User"], path)
    (path / "notes.md").write_text("# hello\n", encoding="utf-8")
    (path / "bench").mkdir()
    (path / "bench" / "result.txt").write_text("score=0.9\n", encoding="utf-8")
    (path / "bench" / "plot.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-qm", "initial"], path)
    return path


@pytest.fixture
def env(tmp_path):
    """A git repo holding a run under ``<repo>/.arctx/runs``."""
    repo = _init_repo(tmp_path / "repo")
    store_dir = str(repo / ".arctx" / "runs")
    result = run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="asset_run",
        store_dir=store_dir,
    )
    store = resolve_store(store_dir)
    return repo, store, "asset_run", result["root_node_id"]


def _attach(store, run_id, root, path, *, title=None):
    handle = store.load_run(run_id)
    result = handle.attach_asset(root, path, repo_root=_repo_of(store, run_id), title=title)
    store.save_run(handle)
    return result.payload.payload_id


def _repo_of(store, run_id):
    return Path(store.run_path(run_id)).parents[2]


def _get(store, run_id, route, **query):
    return dispatch(
        store, run_id, "GET", route, None,
        user_id="tester", lane_id="ws_test", query=query,
    )


class TestAssetView:
    def test_file_asset_resolves(self, env):
        repo, store, run_id, root = env
        pid = _attach(store, run_id, root, "bench/result.txt", title="result")

        status, body = _get(store, run_id, "/asset", payload_id=pid)
        assert status == 200
        assert body["asset"]["path"] == "bench/result.txt"
        assert body["asset"]["title"] == "result"
        assert body["resolution"]["status"] == "ok"
        assert body["resolution"]["kind"] == "blob"
        assert body["resolution"]["content_type"].startswith("text/plain")

    def test_directory_asset_resolves_as_tree(self, env):
        repo, store, run_id, root = env
        pid = _attach(store, run_id, root, "bench")

        status, body = _get(store, run_id, "/asset", payload_id=pid)
        assert status == 200
        assert body["resolution"]["kind"] == "tree"

    def test_payload_id_is_required(self, env):
        _, store, run_id, _ = env
        status, body = _get(store, run_id, "/asset")
        assert status == 400
        assert "payload_id" in body["error"]

    def test_unknown_payload_id(self, env):
        _, store, run_id, _ = env
        status, body = _get(store, run_id, "/asset", payload_id="pl_nope")
        assert status == 404
        assert body["code"] == "unknown_payload"

    def test_non_asset_payload_is_rejected(self, env):
        _, store, run_id, root = env
        from arctx.core.schema.payloads import NodePayload

        handle = store.load_run(run_id)
        payload = handle.attach(root, NodePayload(payload_id="p", target_id=root, type="note"))
        store.save_run(handle)

        status, body = _get(store, run_id, "/asset", payload_id=payload.payload_id)
        assert status == 400
        assert body["code"] == "not_an_asset"

    def test_missing_commit_reports_structured_status(self, env):
        repo, store, run_id, root = env
        handle = store.load_run(run_id)
        broken = AssetPayload(
            payload_id=handle._next_id("pl"),
            target_id=root,
            target_kind="node",
            commit="0" * 40,
            path="notes.md",
        )
        handle.run_graph.attach_payload(broken)
        store.save_run(handle)

        status, body = _get(store, run_id, "/asset", payload_id=broken.payload_id)
        assert status == 200
        assert body["resolution"]["status"] == "missing_commit"
        assert body["resolution"]["kind"] is None


class TestAssetContent:
    def test_text_file_is_inline_utf8(self, env):
        _, store, run_id, root = env
        pid = _attach(store, run_id, root, "bench/result.txt")

        status, body = _get(store, run_id, "/asset/content", payload_id=pid)
        assert status == 200
        assert body["encoding"] == "utf-8"
        assert body["content"] == "score=0.9\n"
        assert body["size"] == len("score=0.9\n")

    def test_binary_file_is_base64(self, env):
        _, store, run_id, root = env
        pid = _attach(store, run_id, root, "bench/plot.png")

        status, body = _get(store, run_id, "/asset/content", payload_id=pid)
        assert status == 200
        assert body["encoding"] == "base64"
        assert body["content_type"] == "image/png"
        assert base64.b64decode(body["content"]) == b"\x89PNG\r\n\x1a\n\x00\xff"

    def test_sub_path_inside_a_directory_asset(self, env):
        _, store, run_id, root = env
        pid = _attach(store, run_id, root, "bench")

        status, body = _get(store, run_id, "/asset/content", payload_id=pid, path="result.txt")
        assert status == 200
        assert body["path"] == "bench/result.txt"
        assert body["content"] == "score=0.9\n"

    def test_sub_path_cannot_escape_the_asset(self, env):
        _, store, run_id, root = env
        pid = _attach(store, run_id, root, "bench")

        status, body = _get(store, run_id, "/asset/content", payload_id=pid, path="../notes.md")
        assert status == 400
        assert body["code"] == "bad_path"

    def test_directory_content_is_refused(self, env):
        _, store, run_id, root = env
        pid = _attach(store, run_id, root, "bench")

        status, body = _get(store, run_id, "/asset/content", payload_id=pid)
        assert status == 400
        assert body["code"] == "not_a_blob"

    def test_missing_path_at_commit(self, env):
        _, store, run_id, root = env
        pid = _attach(store, run_id, root, "bench")

        status, body = _get(store, run_id, "/asset/content", payload_id=pid, path="nope.txt")
        assert status == 404
        assert body["code"] == "missing_path"


class TestAssetEntries:
    def test_directory_listing(self, env):
        _, store, run_id, root = env
        pid = _attach(store, run_id, root, "bench")

        status, body = _get(store, run_id, "/asset/entries", payload_id=pid)
        assert status == 200
        assert body["path"] == "bench"
        names = [e["name"] for e in body["entries"]]
        assert names == ["plot.png", "result.txt"]
        assert all(e["kind"] == "blob" for e in body["entries"])
        assert body["entries"][0]["path"] == "bench/plot.png"

    def test_root_tree_asset(self, env):
        _, store, run_id, root = env
        pid = _attach(store, run_id, root, ".")

        status, body = _get(store, run_id, "/asset/entries", payload_id=pid)
        assert status == 200
        assert body["path"] == ""
        names = [e["name"] for e in body["entries"]]
        assert "bench" in names and "notes.md" in names

    def test_file_listing_is_refused(self, env):
        _, store, run_id, root = env
        pid = _attach(store, run_id, root, "notes.md")

        status, body = _get(store, run_id, "/asset/entries", payload_id=pid)
        assert status == 400
        assert body["code"] == "not_a_tree"


class TestAssetRaw:
    def test_raw_bytes_are_binary_safe(self, env):
        _, store, run_id, root = env
        from arctx.serve.assets import asset_raw

        pid = _attach(store, run_id, root, "bench/plot.png")
        handle = store.load_run(run_id)
        raw = asset_raw(handle, store.run_path(run_id), pid)
        assert raw.data == b"\x89PNG\r\n\x1a\n\x00\xff"
        assert raw.content_type == "image/png"
