"""Tests for the arctx-web HTTP server.

Uses a tiny fake static dir (so no real frontend build is needed) and a real
ThreadingHTTPServer on an ephemeral port. Verifies that API routes delegate to
the shared dispatcher and that everything else is served statically with an SPA
fallback.
"""

from __future__ import annotations

import json
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from arctx.session import resolve_store
from arctx.ext.enabled import EnabledExtension, save_enabled
from arctx_cli.commands.init import run_init_command
from arctx_web import extensions as web_extensions
from arctx_web.assets import find_static_dir
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
    def __init__(self, store, run_id, static_dir, extension_scripts=()):
        handler = build_handler(
            store, run_id, static_dir=static_dir,
            user_id="tester", work_session_id="ws_test",
            extension_scripts=extension_scripts,
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


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
