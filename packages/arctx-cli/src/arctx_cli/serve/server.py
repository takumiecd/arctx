"""Thin ``http.server`` shell around :func:`arctx_cli.serve.api.dispatch`.

Stdlib only. The handler does just three things: read the JSON body, call
``dispatch``, and write the JSON response (with CORS headers so a frontend dev
server on another origin can talk to it). All routing/verb logic lives in
``api.py``; keep this module dumb.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from arctx_cli.serve.api import dispatch


def _make_handler(store: Any, run_id: str, *, user_id: str,
                  work_session_id: str, cors_origin: str):
    class _Handler(BaseHTTPRequestHandler):
        # Quiet by default; the CLI prints its own startup line.
        def log_message(self, *_: Any) -> None:  # noqa: D401
            pass

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self) -> None:  # noqa: N802 (stdlib naming)
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

        def _handle(self, method: str) -> None:
            path = self.path.split("?", 1)[0]
            try:
                body = self._read_body()
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": f"invalid JSON body: {exc}"})
                return
            ws_id = (
                self.headers.get("X-Arctx-Work-Session-Id")
                or self.headers.get("X-Arctx-Lane-Id")
                or work_session_id
            )
            status, payload = dispatch(
                store, run_id, method, path, body,
                user_id=user_id, work_session_id=ws_id,
            )
            self._send(status, payload)

        def _handle_asset(self, path: str) -> None:
            filename = path[len("/assets/"):]
            if ".." in filename or filename.startswith("/") or filename.startswith("."):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid asset path")
                return

            run_path = store.run_path(run_id)
            asset_file = run_path / "assets" / filename
            if not asset_file.exists() or not asset_file.is_file():
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Asset not found")
                return

            import mimetypes
            mime_type, _ = mimetypes.guess_type(asset_file.name)
            if not mime_type:
                mime_type = "application/octet-stream"

            try:
                data = asset_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.end_headers()
                self.wfile.write(data)
            except OSError as exc:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(exc).encode("utf-8"))

        def _handle_upload(self) -> None:
            import email
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self._send(400, {"error": "Content-Type must be multipart/form-data"})
                return

            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                self._send(400, {"error": "Content-Length is 0"})
                return

            raw_data = self.rfile.read(length)
            msg_bytes = b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + raw_data
            msg = email.message_from_bytes(msg_bytes)

            if not msg.is_multipart():
                self._send(400, {"error": "Not a multipart request"})
                return

            file_part = None
            for part in msg.walk():
                if part.get_filename():
                    file_part = part
                    break

            if file_part is None:
                self._send(400, {"error": "No file found in request"})
                return

            filename = file_part.get_filename()
            file_content = file_part.get_payload(decode=True)
            if not file_content:
                self._send(400, {"error": "Empty file content"})
                return

            from arctx.core.ids import opaque_id
            import mimetypes
            
            asset_id = opaque_id("ast")
            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = "application/octet-stream"
            size_bytes = len(file_content)

            run_path = store.run_path(run_id)
            assets_dir = run_path / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)

            dest_filename = f"{asset_id}_{filename}"
            dest_path = assets_dir / dest_filename
            dest_path.write_bytes(file_content)

            self._send(201, {
                "asset_id": asset_id,
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "path": f"assets/{dest_filename}"
            })

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path.startswith("/assets/"):
                self._handle_asset(path)
            else:
                self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/assets/upload":
                self._handle_upload()
            else:
                self._handle("POST")

    return _Handler


def serve(
    store: Any,
    run_id: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    user_id: str = "user",
    work_session_id: str = "default",
    cors_origin: str = "*",
) -> None:
    """Run a blocking HTTP server exposing one run for read/write.

    Returns only when interrupted (Ctrl-C). Binds ``host``/``port`` and serves
    until then.
    """
    handler = _make_handler(
        store, run_id,
        user_id=user_id, work_session_id=work_session_id, cors_origin=cors_origin,
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"arctx serve: http://{host}:{port}  (run {run_id})")
    print("  GET /run · POST /step · POST /attach · POST /cut")
    print("  POST /lane · POST /lane/adopt · GET /health")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\narctx serve: stopped")
    finally:
        httpd.server_close()
