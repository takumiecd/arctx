"""The guard, through a real socket.

The unit tests pin the policy; this pins the wiring. A missing `_refused()`
call in one verb is invisible to a policy test and is exactly the kind of thing
that comes back.
"""

from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from arctx import init
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.serve.guard import RequestGuard
from arctx.serve.server import _make_handler
from arctx.storage.jsonl import JsonlRunStore

EVIL = "https://evil.example"


@pytest.fixture()
def server():
    with tempfile.TemporaryDirectory() as td:
        run = init(Requirement(requirement_id="r", target_type="task", target_id="t"),
                   run_id="guarded")
        run.add_step([run.root_node_id], StepPayload(payload_id="_", target_id="_", type="experiment"))
        store = JsonlRunStore(td)
        store.save_run(run)

        handler = _make_handler(store, "guarded", user_id="u", lane_id="default",
                                guard=RequestGuard())
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_address[1]
        try:
            yield f"http://127.0.0.1:{port}", run.root_node_id
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


def _call(base, path, *, method="GET", body=None, origin=None, host=None,
          content_type="application/json"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", content_type)
    if origin:
        req.add_header("Origin", origin)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.headers.get("Access-Control-Allow-Origin")
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, exc.headers.get("Access-Control-Allow-Origin")


def test_a_website_cannot_read_the_run(server):
    base, _ = server
    assert _call(base, "/run", origin=EVIL) == (403, None)


def test_a_website_cannot_write_a_step(server):
    base, root = server
    status, _ = _call(base, "/step", method="POST", origin=EVIL,
                      body={"input_node_ids": [root], "type": "planted"})
    assert status == 403


def test_a_website_cannot_write_without_a_preflight(server):
    """text/plain is a CORS simple request: the browser never asks permission."""
    base, root = server
    status, _ = _call(base, "/step", method="POST", origin=EVIL,
                      body={"input_node_ids": [root], "type": "planted"},
                      content_type="text/plain;charset=UTF-8")
    assert status == 403


def test_a_website_cannot_cut_records(server):
    base, root = server
    status, _ = _call(base, "/cut", method="POST", origin=EVIL,
                      body={"target_id": root, "target_kind": "node"})
    assert status == 403


def test_the_preflight_itself_is_refused(server):
    base, _ = server
    assert _call(base, "/step", method="OPTIONS", origin=EVIL) == (403, None)


def test_a_rebound_hostname_is_refused(server):
    base, _ = server
    assert _call(base, "/health", host="attacker.example") == (403, None)


def test_the_gui_still_reads(server):
    base, _ = server
    status, acao = _call(base, "/run", origin=base)
    assert status == 200
    assert acao == base


def test_a_local_tool_with_no_origin_still_reads(server):
    base, _ = server
    assert _call(base, "/run") == (200, None)


def test_a_local_page_still_writes(server):
    base, root = server
    status, _ = _call(base, "/step", method="POST", origin=base,
                      body={"input_node_ids": [root], "type": "local"})
    assert status == 201
