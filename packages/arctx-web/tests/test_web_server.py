"""Tests for the arctx-web HTTP server.

Uses a tiny fake static dir (so no real frontend build is needed) and a real
ThreadingHTTPServer on an ephemeral port. Verifies that API routes delegate to
the shared dispatcher and that everything else is served statically with an SPA
fallback.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import arctx as arctx
import pytest
from arctx.core.schema.requirements import Requirement
from arctx.ext.enabled import EnabledExtension, save_enabled
from arctx.ext.git.payloads import DiffSummary, GitChangePayload, RepoPayload
from arctx.session import resolve_store
from arctx_cli.commands.init import run_init_command

from arctx_web import extensions as web_extensions
from arctx_web.assets import find_static_dir
from arctx_web.extensions import WebRoute
from arctx_web.server import build_handler


def _make_run(td: str):
    store_dir = str(Path(td) / "runs")
    result = run_init_command(
        requirement_id="req1", target_type="task", target_id="t",
        run_id="gui_run", store_dir=store_dir,
    )
    return resolve_store(store_dir), "gui_run", result["root_node_id"]


def _fake_static(td: str) -> Path:
    static = Path(td) / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (static / "asset.js").write_text("console.log(1)", encoding="utf-8")
    return static


class _Server:
    def __init__(self, store, run_id, static_dir, extension_scripts=(), extension_routes=()):
        handler = build_handler(
            store, run_id, static_dir=static_dir,
            user_id="tester", work_session_id="ws_test",
            extension_scripts=extension_scripts,
            extension_routes=extension_routes,
        )
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path: str):
        with urllib.request.urlopen(self.url(path)) as r:
            return r.status, r.read(), r.headers.get("Content-Type")

    def post(self, path: str, obj: dict):
        req = urllib.request.Request(
            self.url(path), data=json.dumps(obj).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())

    def put(self, path: str, obj: dict):
        req = urllib.request.Request(
            self.url(path), data=json.dumps(obj).encode(),
            headers={"Content-Type": "application/json"}, method="PUT",
        )
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())


class TestStatic:
    def test_index_served_at_root(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body, ctype = s.get("/")
                assert status == 200
                assert b"<title>app</title>" in body
                assert "text/html" in ctype

    def test_asset_served(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body, _ = s.get("/asset.js")
                assert status == 200
                assert b"console.log" in body

    def test_spa_fallback_for_unknown_path(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body, _ = s.get("/some/client/route")
                assert status == 200
                assert b"<title>app</title>" in body

    def test_extension_scripts_injected_into_index(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            script = "window.arctxWebExtensions = window.arctxWebExtensions || [];"
            with _Server(store, run_id, _fake_static(td), extension_scripts=[script]) as s:
                status, body, ctype = s.get("/")
                assert status == 200
                assert "text/html" in ctype
                assert b"data-arctx-web-extension" in body
                assert script.encode() in body

    def test_extension_scripts_not_injected_into_assets(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            with _Server(store, run_id, _fake_static(td), extension_scripts=["window.x = 1;"]) as s:
                status, body, _ = s.get("/asset.js")
                assert status == 200
                assert body == b"console.log(1)"

    def test_artifact_served_from_run_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            art = store.run_path(run_id) / "artifacts" / "plots"
            art.mkdir(parents=True)
            (art / "loss.png").write_bytes(b"fakepng")
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body, ctype = s.get("/artifacts/plots/loss.png")
                assert status == 200
                assert body == b"fakepng"
                assert "image/png" in ctype


class TestApiDelegation:
    def test_health(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body, _ = s.get("/health")
                assert status == 200
                assert json.loads(body)["status"] == "ok"

    def test_get_run_contract(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body, ctype = s.get("/run")
                assert status == 200
                assert "application/json" in ctype
                doc = json.loads(body)
                assert doc["root_node_id"] == root

    def test_post_step_writes(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body = s.post("/step", {"input_node_ids": [root], "type": "x"})
                assert status == 201
                assert body["step"]["input_node_ids"] == [root]

    def test_post_node_routes_to_api(self):
        # Regression: /node must be treated as an API route, not a static path.
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body = s.post("/node", {})
                assert status == 201
                assert "node" in body

    def test_web_extension_route(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            route = WebRoute(
                method="POST",
                path="/web/ext/demo/echo",
                handler=lambda req: (200, {"ok": True, "body": req.body}),
            )
            with _Server(store, run_id, _fake_static(td), extension_routes=[route]) as s:
                status, body = s.post("/web/ext/demo/echo", {"x": 1})
                assert status == 200
                assert body == {"ok": True, "body": {"x": 1}}

    def test_post_artifacts_upload(self):
        import base64
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                content = b"my uploaded file contents"
                b64_content = base64.b64encode(content).decode()
                status, body = s.post("/artifacts/upload", {
                    "filename": "hello.txt",
                    "file_data": b64_content
                })
                assert status == 201
                assert body["filename"] == "hello.txt"
                assert body["size_bytes"] == len(content)
                assert body["path"].startswith("artifacts/")

                # Verify it can be downloaded
                status_get, body_get, ctype_get = s.get("/" + body["path"])
                assert status_get == 200
                assert body_get == content
                assert "text/plain" in ctype_get


class TestRunSwitching:
    def _second_run(self, store_dir: str):
        result = run_init_command(
            requirement_id="req2", target_type="task", target_id="t2",
            run_id="other_run", store_dir=store_dir,
        )
        return "other_run", result["root_node_id"]

    def test_runs_lists_all_runs(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            self._second_run(str(Path(td) / "runs"))
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body, _ = s.get("/runs")
                assert status == 200
                ids = {r["run_id"] for r in json.loads(body)["runs"]}
                assert {"gui_run", "other_run"} <= ids

    def test_run_query_targets_other_run(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root_a = _make_run(td)
            other_id, root_b = self._second_run(str(Path(td) / "runs"))
            with _Server(store, run_id, _fake_static(td)) as s:
                # No override -> bound run.
                _, body, _ = s.get("/run")
                assert json.loads(body)["root_node_id"] == root_a
                # ?run= override -> the other run's document.
                _, body_b, _ = s.get(f"/run?run={other_id}")
                doc_b = json.loads(body_b)
                assert doc_b["run_id"] == other_id
                assert doc_b["root_node_id"] == root_b

    def test_post_runs_creates_and_serves(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body = s.post("/runs", {"run_id": "made_in_web"})
                assert status == 201
                assert body["run"]["run_id"] == "made_in_web"
                # Listed and reachable via the run override.
                _, listing, _ = s.get("/runs")
                assert "made_in_web" in {r["run_id"] for r in json.loads(listing)["runs"]}
                _, doc, _ = s.get("/run?run=made_in_web")
                assert json.loads(doc)["run_id"] == "made_in_web"

    def test_unknown_run_override_falls_back_to_bound(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root_a = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                _, body, _ = s.get("/run?run=does_not_exist")
                assert json.loads(body)["root_node_id"] == root_a

    def test_artifact_served_from_overridden_run(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _make_run(td)
            other_id, _ = self._second_run(str(Path(td) / "runs"))
            art = store.run_path(other_id) / "artifacts"
            art.mkdir(parents=True)
            (art / "b.png").write_bytes(b"runB-bytes")
            with _Server(store, run_id, _fake_static(td)) as s:
                # Without the override the file lives in the other run, so 404.
                with pytest.raises(urllib.error.HTTPError) as excinfo:
                    s.get("/artifacts/b.png")
                assert excinfo.value.code == 404
                # With ?run= the artifact resolves against the selected run.
                status_ok, body, _ = s.get(f"/artifacts/b.png?run={other_id}")
                assert status_ok == 200
                assert body == b"runB-bytes"


class TestWebLayoutApi:
    def test_layout_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _make_run(td)
            with _Server(store, run_id, _fake_static(td)) as s:
                status, body, ctype = s.get("/web/layout")
                assert status == 200
                assert "application/json" in ctype
                assert body and json.loads(body) == {"view": "default", "nodes": {}}

                status, saved = s.put(
                    "/web/layout",
                    {
                        "nodes": {
                            root: {"x": 12, "y": 34.5},
                            "bad": {"x": "nope", "y": 1},
                        }
                    },
                )
                assert status == 200
                assert saved == {"view": "default", "nodes": {root: {"x": 12.0, "y": 34.5}}}

                _, body, _ = s.get("/web/layout")
                assert json.loads(body) == saved


class TestAssets:
    def test_env_override(self, monkeypatch):
        with tempfile.TemporaryDirectory() as td:
            static = _fake_static(td)
            monkeypatch.setenv("ARCTX_WEB_STATIC", str(static))
            assert find_static_dir() == static

    def test_env_override_missing_index(self, monkeypatch):
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setenv("ARCTX_WEB_STATIC", td)  # no index.html
            assert find_static_dir() is None


class TestWebExtensions:
    def test_load_enabled_scripts_matches_entry_point_name(self, monkeypatch, tmp_path):
        class _Provider:
            def scripts(self):
                return ["window.fromWebExt = true;"]

        class _EntryPoint:
            def load(self):
                return _Provider

        save_enabled(
            tmp_path,
            [
                EnabledExtension(name="demo", version="0.1"),
                EnabledExtension(name="missing", version="0.1"),
            ],
        )
        monkeypatch.setattr(web_extensions, "_get_entry_points", lambda: {"demo": _EntryPoint()})

        assert web_extensions.load_enabled_scripts(tmp_path) == ["window.fromWebExt = true;"]

    def test_builtin_git_extension_contributes_script_and_route(self, tmp_path):
        save_enabled(tmp_path, [EnabledExtension(name="git", version="0.1")])

        scripts = web_extensions.load_enabled_scripts(tmp_path)
        routes = web_extensions.load_enabled_routes(tmp_path)

        assert any("arctx-git-diff-view" in script for script in scripts)
        assert any(route.path == "/web/ext/git/diff" for route in routes)

    def test_builtin_diagram_extension_contributes_script(self, tmp_path):
        save_enabled(tmp_path, [EnabledExtension(name="diagram", version="0.1")])

        scripts = web_extensions.load_enabled_scripts(tmp_path)

        assert any("arctx-diagram-preview" in script for script in scripts)

    def test_git_diff_route_returns_patch(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "tester@example.com")
        _git(repo, "config", "user.name", "Tester")
        (repo / "hello.txt").write_text("hello\n", encoding="utf-8")
        _git(repo, "add", "hello.txt")
        _git(repo, "commit", "-m", "add hello")
        head = _git(repo, "rev-parse", "HEAD")

        store_dir = tmp_path / "runs"
        store = resolve_store(str(store_dir))
        handle = arctx.init(Requirement("req1", "task", "t"), run_id="git_diff_run")
        handle.run_graph.attach_payload(
            RepoPayload(
                payload_id=handle._next_id("pl"),
                target_id=handle.root_node_id,
                repo_id="repo_1",
                slug="local/repo",
                local_path=str(repo),
            )
        )
        step = handle.add_step(
            [handle.root_node_id],
            GitChangePayload(
                payload_id="pending",
                target_id="pending",
                branch="main",
                head_commit=head,
                diff_summary=DiffSummary(files_changed=1, insertions=1, deletions=0),
                repo_id="repo_1",
            ),
        )
        store.save_run(handle)

        route = next(
            route
            for route in web_extensions.load_enabled_routes(_enabled_dir(tmp_path, "git"))
            if route.path == "/web/ext/git/diff"
        )
        static_dir = _fake_static(str(tmp_path))
        with _Server(store, "git_diff_run", static_dir, extension_routes=[route]) as s:
            status, body = s.post("/web/ext/git/diff", {"step_id": step.step_id})
            assert status == 200
            assert body["head_commit"] == head
            assert "diff --git" in body["diff"]
            assert "+hello" in body["diff"]


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _enabled_dir(tmp_path: Path, name: str) -> Path:
    run_dir = tmp_path / f"enabled_{name}"
    save_enabled(run_dir, [EnabledExtension(name=name, version="0.1")])
    return run_dir


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
