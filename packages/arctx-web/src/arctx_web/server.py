"""HTTP server that serves the GUI: API routes + static frontend.

The API routes are delegated verbatim to :func:`arctx_cli.serve.api.dispatch`
(one source of truth for the data contract). Everything else is served from the
built frontend directory, with an SPA fallback to ``index.html``.
"""

from __future__ import annotations

import json
import mimetypes
import posixpath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from arctx_cli.serve.api import dispatch

# Paths handled by the JSON API; everything else is a static asset request.
API_PATHS = frozenset({"/run", "/step", "/attach", "/cut", "/health"})


def build_handler(
    store: Any,
    run_id: str,
    *,
    static_dir: Path,
    user_id: str,
    work_session_id: str,
    cors_origin: str = "*",
):
    """Build a request handler class bound to one run and a static dir."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        # ----- helpers -----

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _send_json(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        def _send_bytes(self, status: int, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        # ----- routing -----

        def _path(self) -> str:
            return self.path.split("?", 1)[0]

        def _is_api(self) -> bool:
            return self._path() in API_PATHS

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

        def _api(self, method: str) -> None:
            try:
                body = self._read_body()
            except (ValueError, json.JSONDecodeError) as exc:
                self._send_json(400, {"error": f"invalid JSON body: {exc}"})
                return
            status, payload = dispatch(
                store, run_id, method, self._path(), body,
                user_id=user_id, work_session_id=work_session_id,
            )
            self._send_json(status, payload)

        def _resolve_static(self, url_path: str) -> Path:
            # Normalize and confine to static_dir (no path traversal).
            rel = posixpath.normpath(url_path).lstrip("/")
            target = (static_dir / rel).resolve()
            root = static_dir.resolve()
            if target == root or root not in target.parents:
                # Directory or outside root -> SPA fallback.
                return root / "index.html"
            if not target.is_file():
                return root / "index.html"
            return target

        def _serve_static(self) -> None:
            target = self._resolve_static(self._path())
            if not target.is_file():
                self._send_bytes(404, b"not found", "text/plain")
                return
            ctype, _ = mimetypes.guess_type(str(target))
            self._send_bytes(200, target.read_bytes(), ctype or "application/octet-stream")

        # ----- verbs -----

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if self._is_api():
                self._api("GET")
            else:
                self._serve_static()

        def do_POST(self) -> None:  # noqa: N802
            if self._is_api():
                self._api("POST")
            else:
                self._send_json(404, {"error": "not found"})

    return _Handler


def serve_gui(
    store: Any,
    run_id: str,
    *,
    static_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8788,
    user_id: str = "user",
    work_session_id: str = "default",
    cors_origin: str = "*",
    on_ready=None,
) -> None:
    """Run a blocking server that serves the GUI and the run API.

    ``on_ready`` (if given) is called with the bound URL once the socket is
    listening, before the blocking serve loop — used to open a browser.
    """
    handler = build_handler(
        store, run_id, static_dir=static_dir,
        user_id=user_id, work_session_id=work_session_id, cors_origin=cors_origin,
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"arctx-web: {url}  (run {run_id})")
    if on_ready is not None:
        on_ready(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\narctx-web: stopped")
    finally:
        httpd.server_close()
