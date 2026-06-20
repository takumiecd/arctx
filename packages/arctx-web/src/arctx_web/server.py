"""HTTP server that serves the GUI: API routes + static frontend.

The API routes are delegated verbatim to :func:`arctx_cli.serve.api.dispatch`
(one source of truth for the data contract). Everything else is served from the
built frontend directory, with an SPA fallback to ``index.html``.
"""

from __future__ import annotations

import json
import mimetypes
import posixpath
import urllib.parse
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from arctx_cli.serve.api import dispatch

from arctx_web.extensions import WebRequest, WebRoute
from arctx_web.layouts import get_layout, save_layout

# Paths handled by the JSON API; everything else is a static asset request.
API_PATHS = frozenset({"/run", "/node", "/step", "/attach", "/cut", "/health"})
WEB_API_PATHS = frozenset({"/web/layout"})
ARTIFACT_PREFIX = "/artifacts/"


def build_handler(
    store: Any,
    run_id: str,
    *,
    static_dir: Path,
    user_id: str,
    work_session_id: str,
    extension_scripts: list[str] | tuple[str, ...] = (),
    extension_routes: list[WebRoute] | tuple[WebRoute, ...] = (),
    cors_origin: str = "*",
) -> type[BaseHTTPRequestHandler]:
    """Build a request handler class bound to one run and a static dir."""
    route_map = {
        (route.method.upper(), route.path.rstrip("/") or "/"): route.handler
        for route in extension_routes
    }

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        # ----- helpers -----

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
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

        def _is_web_api(self) -> bool:
            path = self._path()
            return path in WEB_API_PATHS or (self.command.upper(), path) in route_map

        def _is_artifact(self) -> bool:
            return self._path().startswith(ARTIFACT_PREFIX)

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

        def _web_api(self, method: str) -> None:
            route = (method.upper(), self._path())
            handler = route_map.get(route)
            if handler is not None:
                try:
                    status, payload = handler(
                        WebRequest(
                            store=store,
                            run_id=run_id,
                            run_dir=store.run_path(run_id),
                            body=self._read_body() or {},
                            user_id=user_id,
                            work_session_id=work_session_id,
                        )
                    )
                    self._send_json(status, payload)
                except (ValueError, json.JSONDecodeError) as exc:
                    self._send_json(400, {"error": str(exc)})
                return
            if self._path() != "/web/layout":
                self._send_json(404, {"error": "not found"})
                return
            run_dir = store.run_path(run_id)
            if method == "GET":
                self._send_json(200, get_layout(run_dir))
                return
            if method == "PUT":
                try:
                    body = self._read_body() or {}
                    self._send_json(200, save_layout(run_dir, body))
                except (ValueError, json.JSONDecodeError) as exc:
                    self._send_json(400, {"error": str(exc)})
                return
            self._send_json(405, {"error": "method not allowed"})

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
            data = target.read_bytes()
            if target.name == "index.html" and extension_scripts:
                data = _inject_extension_scripts(data, extension_scripts)
            self._send_bytes(200, data, ctype or "application/octet-stream")

        def _serve_artifact(self) -> None:
            target = _resolve_artifact(store.run_path(run_id), self._path())
            if target is None or not target.is_file():
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
            elif self._is_web_api():
                self._web_api("GET")
            elif self._is_artifact():
                self._serve_artifact()
            else:
                self._serve_static()

        def do_POST(self) -> None:  # noqa: N802
            if self._is_api():
                self._api("POST")
            elif self._is_web_api():
                self._web_api("POST")
            else:
                self._send_json(404, {"error": "not found"})

        def do_PUT(self) -> None:  # noqa: N802
            if self._is_web_api():
                self._web_api("PUT")
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
    extension_scripts: list[str] | tuple[str, ...] = (),
    extension_routes: list[WebRoute] | tuple[WebRoute, ...] = (),
    cors_origin: str = "*",
    on_ready: Callable[[str], None] | None = None,
) -> None:
    """Run a blocking server that serves the GUI and the run API.

    ``on_ready`` (if given) is called with the bound URL once the socket is
    listening, before the blocking serve loop — used to open a browser.
    """
    handler = build_handler(
        store, run_id, static_dir=static_dir,
        user_id=user_id, work_session_id=work_session_id, cors_origin=cors_origin,
        extension_scripts=extension_scripts,
        extension_routes=extension_routes,
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


def _inject_extension_scripts(data: bytes, scripts: list[str] | tuple[str, ...]) -> bytes:
    html = data.decode("utf-8")
    tags = "\n".join(
        f'<script data-arctx-web-extension>{_escape_script(script)}</script>' for script in scripts
    )
    if not tags:
        return data
    marker = "</head>"
    if marker in html:
        html = html.replace(marker, tags + "\n" + marker, 1)
    elif "</html>" in html:
        html = html.replace("</html>", tags + "\n</html>", 1)
    else:
        html = html + "\n" + tags
    return html.encode("utf-8")


def _escape_script(script: str) -> str:
    return script.replace("</script", "<\\/script")


def _resolve_artifact(run_dir: Path, url_path: str) -> Path | None:
    raw = urllib.parse.unquote(url_path[len(ARTIFACT_PREFIX):])
    rel = posixpath.normpath(raw).lstrip("/")
    if rel in ("", ".") or rel.startswith("../"):
        return None
    root = (run_dir / "artifacts").resolve()
    target = (root / rel).resolve()
    if target == root or root not in target.parents:
        return None
    return target
