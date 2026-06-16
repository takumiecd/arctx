"""Tests for the ``arctx serve`` request dispatcher (socket-free).

Exercises every route through ``dispatch`` directly, so no port is bound.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from arctx.session import resolve_store
from arctx_cli.commands.init import run_init_command
from arctx_cli.serve.api import dispatch


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _setup(td: str, run_id: str = "srv_run"):
    result = run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(td),
    )
    store = resolve_store(_store_dir(td))
    return store, run_id, result["root_node_id"]


def _call(store, run_id, method, path, body=None):
    return dispatch(
        store, run_id, method, path, body,
        user_id="tester", work_session_id="ws_test",
    )


class TestReadRoutes:
    def test_health(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "GET", "/health")
            assert status == 200
            assert body == {"status": "ok", "run_id": run_id}

    def test_get_run_returns_data_contract(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            status, body = _call(store, run_id, "GET", "/run")
            assert status == 200
            assert body["arctx_export_version"] == 1
            assert body["root_node_id"] == root
            assert any(n["node_id"] == root for n in body["nodes"])

    def test_unknown_route(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "GET", "/nope")
            assert status == 404
            assert "error" in body

    def test_unknown_run(self):
        with tempfile.TemporaryDirectory() as td:
            store, _, _ = _setup(td)
            status, body = _call(store, "missing", "GET", "/run")
            assert status == 404
            assert "error" in body


class TestWriteRoutes:
    def test_post_step_then_visible_in_run(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            status, body = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root],
                "type": "experiment",
                "content": {"lr": 0.1},
            })
            assert status == 201
            step_id = body["step"]["step_id"]

            _, run = _call(store, run_id, "GET", "/run")
            step = next(s for s in run["steps"] if s["step_id"] == step_id)
            assert step["input_node_ids"] == [root]
            pl = next(p for p in run["payloads"] if p["target_id"] == step_id)
            assert pl["content"] == {"lr": 0.1}

    def test_post_step_requires_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "POST", "/step", {"type": "x"})
            assert status == 400
            assert "input_node_ids" in body["error"]

    def test_post_attach(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            status, body = _call(store, run_id, "POST", "/attach", {
                "node_id": root,
                "type": "note",
                "content": {"text": "hello"},
            })
            assert status == 201
            assert body["payload"]["content"] == {"text": "hello"}

    def test_post_cut_marks_inactive(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            _, made = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root], "type": "x",
            })
            step_id = made["step"]["step_id"]

            status, _ = _call(store, run_id, "POST", "/cut", {
                "target_id": step_id, "target_kind": "step", "reason": "wrong",
            })
            assert status == 201

            _, run = _call(store, run_id, "GET", "/run")
            step = next(s for s in run["steps"] if s["step_id"] == step_id)
            assert step["inactive"] is True

    def test_post_cut_validates_kind(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            status, body = _call(store, run_id, "POST", "/cut", {
                "target_id": root, "target_kind": "bogus",
            })
            assert status == 400
            assert "target_kind" in body["error"]

    def test_post_node_bare(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "POST", "/node", {})
            assert status == 201
            new_id = body["node"]["node_id"]
            assert "payload" not in body

            _, run = _call(store, run_id, "GET", "/run")
            assert any(n["node_id"] == new_id for n in run["nodes"])

    def test_post_node_with_payload(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "POST", "/node", {
                "type": "note", "content": {"text": "seed"},
            })
            assert status == 201
            assert body["payload"]["content"] == {"text": "seed"}
            node_id = body["node"]["node_id"]

            _, run = _call(store, run_id, "GET", "/run")
            pl = next(p for p in run["payloads"] if p["target_id"] == node_id)
            assert pl["content"] == {"text": "seed"}

    def test_post_attach_to_step(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            _, made = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root], "type": "x",
            })
            step_id = made["step"]["step_id"]

            status, body = _call(store, run_id, "POST", "/attach", {
                "target_id": step_id, "target_kind": "step",
                "type": "metric", "content": {"score": 0.9},
            })
            assert status == 201
            assert body["payload"]["target_kind"] == "step"
            assert body["payload"]["content"] == {"score": 0.9}

            _, run = _call(store, run_id, "GET", "/run")
            pls = [p for p in run["payloads"] if p["target_id"] == step_id]
            assert any(p.get("content") == {"score": 0.9} for p in pls)

    def test_post_step_into_existing_output_node(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            _, made = _call(store, run_id, "POST", "/node", {})
            orphan = made["node"]["node_id"]

            status, body = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root], "output_node_id": orphan, "type": "derive",
            })
            assert status == 201
            assert body["step"]["output_node_id"] == orphan
            assert body["step"]["input_node_ids"] == [root]

    def test_post_step_into_existing_rejects_producer(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            _, made = _call(store, run_id, "POST", "/step", {"input_node_ids": [root]})
            existing_out = made["step"]["output_node_id"]
            status, body = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root], "output_node_id": existing_out,
            })
            assert status == 400
            assert "producing step" in body["error"]

    def test_post_attach_resolves_kind_from_id(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            # No target_kind given -> resolved from the record id (a node).
            status, body = _call(store, run_id, "POST", "/attach", {
                "target_id": root, "type": "note", "content": {"text": "hi"},
            })
            assert status == 201
            assert body["payload"]["target_kind"] == "node"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
