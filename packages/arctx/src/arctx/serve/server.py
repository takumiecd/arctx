"""Thin stdlib HTTP shell around :func:`arctx.serve.api.dispatch`."""

from __future__ import annotations

import json
import mimetypes
import posixpath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from arctx.serve.api import dispatch

ARTIFACT_PREFIX = "/artifacts/"


def _make_handler(store: Any, run_id: str, *, user_id: str, lane_id: str, cors_origin: str):
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, X-Arctx-Run-Id, X-Arctx-Work-Session-Id, X-Arctx-Lane-Id",
            )
            self.end_headers()
            self.wfile.write(data)

        def _send_bytes(self, status: int, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self) -> None:
            self._send(204, {})

        def _read_body(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return None
            raw = self.rfile.read(length)
            if not raw:
                return None
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("request body must be a JSON object")
            return parsed

        def _request_run_id(self) -> str:
            parsed = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            return query.get("run") or self.headers.get("X-Arctx-Run-Id") or run_id

        def _serve_artifact(self) -> None:
            parsed = urlparse(self.path)
            target = _resolve_artifact(store.run_path(self._request_run_id()), parsed.path)
            if target is None or not target.is_file():
                self._send_bytes(404, b"not found", "text/plain; charset=utf-8")
                return
            ctype, _ = mimetypes.guess_type(str(target))
            self._send_bytes(200, target.read_bytes(), ctype or "application/octet-stream")

        def _handle(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                body = self._read_body()
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": f"invalid JSON body: {exc}"})
                return
            request_lane_id = (
                self.headers.get("X-Arctx-Work-Session-Id")
                or self.headers.get("X-Arctx-Lane-Id")
                or lane_id
            )
            request_run_id = query.get("run") or self.headers.get("X-Arctx-Run-Id") or run_id
            status, payload = dispatch(
                store,
                request_run_id,
                method,
                path,
                body,
                user_id=user_id,
                lane_id=request_lane_id,
                query=query,
            )
            self._send(status, payload)

        def do_GET(self) -> None:
            if urlparse(self.path).path.startswith(ARTIFACT_PREFIX):
                self._serve_artifact()
                return
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

    return _Handler


def _resolve_artifact(run_dir: Path, url_path: str) -> Path | None:
    raw = unquote(url_path[len(ARTIFACT_PREFIX):])
    rel = posixpath.normpath(raw).lstrip("/")
    if rel in ("", ".") or rel.startswith("../"):
        return None
    root = (run_dir / "artifacts").resolve()
    target = (root / rel).resolve()
    if target == root or root not in target.parents:
        return None
    return target


def serve(
    store: Any,
    run_id: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    user_id: str = "user",
    lane_id: str = "default",
    cors_origin: str = "*",
) -> None:
    handler = _make_handler(store, run_id, user_id=user_id, lane_id=lane_id, cors_origin=cors_origin)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"arctx serve: http://{host}:{port}  (run {run_id})")
    print("  GET /run · POST /step · POST /attach · POST /cut")
    print("  POST /lane · POST /lane/payload · POST /lane/link · POST /lane/adopt · GET /health")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\narctx serve: stopped")
    finally:
        httpd.server_close()
