"""Thin stdlib HTTP shell around :func:`arctx.serve.api.dispatch`."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from arctx.serve.api import dispatch
from arctx.serve.guard import RequestGuard, guard_from_cors_option


def _make_handler(
    store: Any, run_id: str, *, user_id: str, lane_id: str, guard: RequestGuard
):
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def _cors_headers(self) -> None:
            allow = guard.acao(self.headers.get("Origin"))
            # Vary regardless: the reply differs by Origin even when the answer
            # is "no header", so a shared cache must not reuse it.
            self.send_header("Vary", "Origin")
            if allow is None:
                return
            self.send_header("Access-Control-Allow-Origin", allow)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, X-Arctx-Run-Id, X-Arctx-Work-Session-Id, X-Arctx-Lane-Id",
            )

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(data)

        def _send_bytes(self, status: int, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(data)

        def _refused(self) -> bool:
            """Answer 403 and stop when this request is not ours to serve."""
            reason = guard.reject(
                origin=self.headers.get("Origin"), host=self.headers.get("Host")
            )
            if reason is None:
                return False
            self._send(403, {"error": reason, "code": "forbidden_origin"})
            return True

        def do_OPTIONS(self) -> None:
            if self._refused():
                return
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

        def _serve_asset_raw(self, run_id_for_request: str, query: dict) -> None:
            """Send an asset blob as raw bytes (the one binary route).

            Everything else goes through the pure dispatcher; this exists so
            ``<img src=...>`` works without a base64 round-trip. The resolution
            logic itself is shared with ``GET /asset/content``.
            """
            from arctx.serve.assets import AssetError, asset_raw

            payload_id = query.get("payload_id") or query.get("asset")
            if not payload_id:
                self._send(400, {"error": "payload_id is required"})
                return
            try:
                handle = store.load_run(run_id_for_request)
                raw = asset_raw(handle, store.run_path(run_id_for_request), str(payload_id), query.get("path"))
            except AssetError as exc:
                self._send(exc.status, {"error": exc.message, "code": exc.code})
                return
            except (KeyError, ValueError, OSError) as exc:
                self._send(400, {"error": str(exc)})
                return
            self._send_bytes(200, raw.data, raw.content_type)

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
            if method == "GET" and path.rstrip("/") == "/asset/raw":
                self._serve_asset_raw(request_run_id, query)
                return
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
            if self._refused():
                return
            self._handle("GET")

        def do_POST(self) -> None:
            if self._refused():
                return
            self._handle("POST")

    return _Handler


def serve(
    store: Any,
    run_id: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    user_id: str = "user",
    lane_id: str = "default",
    cors_origin: str | None = None,
) -> None:
    guard = guard_from_cors_option(cors_origin)
    handler = _make_handler(store, run_id, user_id=user_id, lane_id=lane_id, guard=guard)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"arctx serve: http://{host}:{port}  (run {run_id})")
    if guard.allow_any_origin:
        print("  WARNING: --cors-origin '*' lets any website in your browser read and")
        print("           write this run for as long as this server is up.")
    print("  GET /run · POST /step · POST /attach · POST /cut")
    print("  POST /lane · GET /health")
    print("  GET /asset · /asset/entries · /asset/content · /asset/raw")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\narctx serve: stopped")
    finally:
        httpd.server_close()
