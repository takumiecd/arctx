"""Tests for the ``arctx serve`` request dispatcher (socket-free).

Exercises every route through ``dispatch`` directly, so no port is bound.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from arctx.core.lanes import validate_lanes
from arctx.core.schema.graph import Node
from arctx.session import resolve_store

from arctx_cli.commands.init import run_init_command
from arctx_cli.serve.api import dispatch


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _seed_orphan(store, run_id, *, work_session_id: str = "ws_test") -> str:
    """Mint a producer-less node low-level, joined to *work_session_id*'s lane.

    No serve route mints standalone nodes anymore (POST /node is gone); a
    producer-less node only arises from the run root or an imported subgraph.
    This builds one directly — recording the matching ``node_added`` work event
    so it has lane provenance — so the step output_node_id route can be exercised.
    """
    handle = store.load_run(run_id)
    node = Node(node_id=handle._next_id("n"))
    handle.run_graph.add_node(node)
    handle.record_work_event(
        user_id="tester",
        work_session_id=work_session_id,
        event_type="node_added",
        target_kind="node",
        target_id=node.node_id,
        created_records=(node.node_id,),
    )
    store.save_run(handle)
    return node.node_id


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
    return _call_as(store, run_id, method, path, body, work_session_id="ws_test")


def _call_as(store, run_id, method, path, body=None, *, work_session_id: str):
    return dispatch(
        store, run_id, method, path, body,
        user_id="tester", work_session_id=work_session_id,
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
            assert body["current_lane_id"] == "ws_test"
            assert body["current_lane_name"] == "ws_test"
            assert any(n["node_id"] == root for n in body["nodes"])

    def test_get_runs_lists_store(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            run_init_command(
                requirement_id="req2", target_type="code", target_id="t2",
                run_id="srv_run_2", store_dir=_store_dir(td),
            )
            status, body = _call(store, run_id, "GET", "/runs")
            assert status == 200
            ids = {r["run_id"] for r in body["runs"]}
            assert {run_id, "srv_run_2"} <= ids
            assert body["current_run_id"] == run_id

    def test_post_runs_creates_run(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "POST", "/runs", {"run_id": "fresh_run"})
            assert status == 201
            assert body["run"]["run_id"] == "fresh_run"
            assert store.run_path("fresh_run").exists()
            # It now shows up in the listing.
            _, listing = _call(store, run_id, "GET", "/runs")
            assert "fresh_run" in {r["run_id"] for r in listing["runs"]}
            # And it can be served immediately.
            status, doc = _call(store, "fresh_run", "GET", "/run")
            assert status == 200
            assert doc["run_id"] == "fresh_run"

    def test_post_runs_requires_name(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "POST", "/runs", {})
            assert status == 400
            assert "run_id" in body["error"]

    def test_post_runs_rejects_unsafe_id(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "POST", "/runs", {"run_id": "../escape"})
            assert status == 400
            assert "run_id" in body["error"]

    def test_post_runs_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "POST", "/runs", {"run_id": run_id})
            assert status == 400
            assert "already exists" in body["error"]

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

    def test_post_step_rejects_second_lane_root(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            status, _ = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root], "type": "first",
            })
            assert status == 201

            status, body = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root], "type": "second",
            })
            assert status == 400
            assert "multiple_lane_roots" in body["error"]

            handle = store.load_run(run_id)
            assert len(handle.run_graph.steps) == 1

    def test_writes_tolerate_preexisting_lane_errors(self):
        # Legacy runs created before lane provenance carry records with no lane
        # membership. A write must not be blocked by those pre-existing errors;
        # only errors the write itself introduces should block it.
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            status, made = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root], "type": "x",
            })
            assert status == 201

            # Strip lane provenance to simulate a pre-lane run, then drop any
            # cached graph so the store reloads the legacy-shaped records.
            run_dir = Path(store.run_path(run_id))
            (run_dir / "work_events.jsonl").write_text("")
            cache = run_dir / "run.cache.pkl"
            if cache.exists():
                cache.unlink()

            legacy = store.load_run(run_id)
            assert any(
                issue.code == "step_without_lane"
                for issue in validate_lanes(
                    legacy.run_graph, root_node_id=legacy.root_node_id
                )
            )

            # Creating a lane and adding records into it still succeeds despite
            # the pre-existing legacy violations.
            status, body = _call(store, run_id, "POST", "/lane", {"name": "L1"})
            assert status == 201
            lane_id = body["lane"]["work_session_id"]

            status, _ = _call_as(
                store, run_id, "POST", "/step",
                {"input_node_ids": [root], "type": "y"},
                work_session_id=lane_id,
            )
            assert status == 201

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
            orphan = _seed_orphan(store, run_id)

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

    def test_post_lane_create_then_visible_in_run(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "POST", "/lane", {"name": "math"})
            assert status == 201
            assert body["lane"]["name"] == "math"
            lane_id = body["lane"]["work_session_id"]

            _, run = _call(store, run_id, "GET", "/run")
            assert any(lane["work_session_id"] == lane_id for lane in run["lanes"])

    def test_post_lane_create_rejects_duplicate_name(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, _ = _call(store, run_id, "POST", "/lane", {"name": "math"})
            assert status == 201

            status, body = _call(store, run_id, "POST", "/lane", {"name": "math"})
            assert status == 400
            assert "already exists" in body["error"]

    def test_post_lane_adopt_explicit_records(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            _, lane_body = _call(store, run_id, "POST", "/lane", {"name": "math"})
            lane_id = lane_body["lane"]["work_session_id"]
            _, made = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root],
                "type": "derive",
            })
            step_id = made["step"]["step_id"]
            output_id = made["step"]["output_node_id"]

            status, body = _call(store, run_id, "POST", "/lane/adopt", {
                "lane_id": lane_id,
                "record_ids": [step_id, output_id],
                "reason": "manual repair",
            })
            assert status == 201
            assert body["lane_id"] == lane_id
            assert body["adopted_record_ids"] == [step_id, output_id]
            assert body["mode"] == "explicit"

            _, run = _call(store, run_id, "GET", "/run")
            prov = run["record_provenance"][step_id]
            assert prov["lane_id"] == lane_id
            assert prov["membership_kind"] == "adopted"
            assert prov["event_type"] == "lane_adopted"

    def test_post_lane_adopt_by_name_history(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            _call(store, run_id, "POST", "/lane", {"name": "math"})
            _, made = _call(store, run_id, "POST", "/step", {
                "input_node_ids": [root],
                "type": "derive",
            })
            output_id = made["step"]["output_node_id"]

            status, body = _call(store, run_id, "POST", "/lane/adopt", {
                "name": "math",
                "history_node_id": output_id,
            })
            assert status == 201
            assert body["mode"] == "history"
            assert output_id in body["adopted_record_ids"]

    def test_post_lane_adopt_unknown_lane(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            status, body = _call(store, run_id, "POST", "/lane/adopt", {
                "lane_id": "missing",
                "record_ids": [root],
            })
            assert status == 404
            assert "unknown lane" in body["error"]

    def test_post_lane_adopt_requires_one_source(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            _, lane_body = _call(store, run_id, "POST", "/lane", {"name": "math"})
            status, body = _call(store, run_id, "POST", "/lane/adopt", {
                "lane_id": lane_body["lane"]["work_session_id"],
                "record_ids": [root],
                "history_node_id": root,
            })
            assert status == 400
            assert "exactly one" in body["error"]

    def test_post_lane_adopt_rejects_multiple_lane_roots(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root = _setup(td)
            _, math_body = _call(store, run_id, "POST", "/lane", {"name": "math"})
            _, exp_body = _call(store, run_id, "POST", "/lane", {"name": "experiment"})
            math_id = math_body["lane"]["work_session_id"]
            exp_id = exp_body["lane"]["work_session_id"]

            _, math_root = _call_as(store, run_id, "POST", "/step", {
                "input_node_ids": [root], "type": "math",
            }, work_session_id=math_id)
            math_node = math_root["step"]["output_node_id"]
            _call_as(store, run_id, "POST", "/step", {
                "input_node_ids": [math_node], "type": "experiment",
            }, work_session_id=exp_id)
            _, other = _call_as(store, run_id, "POST", "/step", {
                "input_node_ids": [math_node], "type": "other",
            }, work_session_id=math_id)

            status, body = _call(store, run_id, "POST", "/lane/adopt", {
                "lane_id": exp_id,
                "record_ids": [
                    other["step"]["step_id"],
                    other["step"]["output_node_id"],
                ],
            })

            assert status == 400
            assert "multiple_lane_roots" in body["error"]
            handle = store.load_run(run_id)
            assert not any(
                issue.severity == "error"
                for issue in validate_lanes(
                    handle.run_graph,
                    root_node_id=handle.root_node_id,
                )
            )


class TestExtensionRoutes:
    def test_get_ext(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "GET", "/ext")
            assert status == 200
            assert "extensions" in body
            assert any(ext["name"] == "git" for ext in body["extensions"])

    def test_post_ext_enable_disable(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(store, run_id, "POST", "/ext/enable", {"name": "git"})
            assert status == 200
            assert body["status"] in ("enabled", "already_enabled")

            status, body = _call(store, run_id, "GET", "/ext")
            git_ext = next(ext for ext in body["extensions"] if ext["name"] == "git")
            assert git_ext["enabled"] is True

            status, body = _call(store, run_id, "POST", "/ext/disable", {"name": "git"})
            assert status == 200
            assert body["status"] == "disabled"

            status, body = _call(store, run_id, "GET", "/ext")
            git_ext = next(ext for ext in body["extensions"] if ext["name"] == "git")
            assert git_ext["enabled"] is False


class TestArtifactUpload:
    @staticmethod
    def _b64(data: bytes = b"hello") -> str:
        import base64

        return base64.b64encode(data).decode()

    def test_upload_writes_flat_file(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, body = _call(
                store, run_id, "POST", "/artifacts/upload",
                {"filename": "chart.png", "file_data": self._b64()},
            )
            assert status == 201
            assert body["filename"] == "chart.png"
            assert body["path"].startswith("artifacts/art_")
            written = store.run_path(run_id) / body["path"]
            assert written.is_file()

    def test_upload_strips_path_components(self):
        # A filename with separators / .. must never escape artifacts/.
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            artifacts = (store.run_path(run_id) / "artifacts").resolve()
            for hostile in ("../../../etc/passwd", "a/b.txt", "/abs/evil"):
                status, body = _call(
                    store, run_id, "POST", "/artifacts/upload",
                    {"filename": hostile, "file_data": self._b64()},
                )
                assert status == 201
                assert "/" not in body["filename"]
                written = (store.run_path(run_id) / body["path"]).resolve()
                assert artifacts in written.parents

    def test_upload_rejects_bare_dotdot_filename(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _setup(td)
            status, _ = _call(
                store, run_id, "POST", "/artifacts/upload",
                {"filename": "..", "file_data": self._b64()},
            )
            assert status == 400

    def test_upload_unknown_run_is_404(self):
        with tempfile.TemporaryDirectory() as td:
            store, _, _ = _setup(td)
            status, _ = _call(
                store, "run_missing", "POST", "/artifacts/upload",
                {"filename": "x.txt", "file_data": self._b64()},
            )
            assert status == 404
            assert not store.run_path("run_missing").exists()


class TestVisibleAssets:
    @staticmethod
    def _attach_asset(handle, target_kind, target_id, name):
        from arctx.core.schema.payloads import AssetPayload

        payload = AssetPayload(
            payload_id=handle._next_id("pl"),
            target_id=target_id,
            target_kind=target_kind,
            asset_id=f"ast_{name}",
            filename=f"{name}.png",
            mime_type="image/png",
            size_bytes=1,
            path=f"artifacts/ast_{name}.png",
        )
        handle.run_graph.attach_payload(payload)
        return payload

    def _setup_assets(self, td):
        from arctx.core.schema.payloads import StepPayload

        store_dir = _store_dir(td)
        run_init_command(
            requirement_id="r", target_type="task", target_id="t",
            run_id="srv_assets", store_dir=store_dir,
        )
        store = resolve_store(store_dir)
        handle = store.load_run("srv_assets")
        root = handle.root_node_id
        sp = lambda: StepPayload(payload_id="_", target_id="_", type="x")  # noqa: E731
        n1 = handle.add_step([root], sp()).output_node_id
        n2 = handle.add_step([root], sp()).output_node_id
        self._attach_asset(handle, "node", root, "root")
        self._attach_asset(handle, "node", n1, "n1")
        self._attach_asset(handle, "node", n2, "n2")
        store.save_run(handle)
        return store, "srv_assets", root, n1, n2

    def _visible(self, store, run_id, from_id):
        return dispatch(
            store, run_id, "GET", "/assets/visible", None,
            user_id="t", work_session_id="ws", query={"from": from_id},
        )

    def test_returns_ancestors_and_self_only(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _root, n1, _n2 = self._setup_assets(td)
            status, body = self._visible(store, run_id, n1)
            assert status == 200
            names = {a["filename"] for a in body["assets"]}
            # root (ancestor) + n1 (self); NOT n2 (sibling)
            assert names == {"root.png", "n1.png"}

    def test_root_sees_only_itself(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, root, _n1, _n2 = self._setup_assets(td)
            status, body = self._visible(store, run_id, root)
            assert status == 200
            assert {a["filename"] for a in body["assets"]} == {"root.png"}

    def test_missing_from_is_400(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, *_ = self._setup_assets(td)
            status, _ = dispatch(
                store, run_id, "GET", "/assets/visible", None,
                user_id="t", work_session_id="ws", query={},
            )
            assert status == 400

    def test_unknown_record_is_404(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, *_ = self._setup_assets(td)
            status, _ = self._visible(store, run_id, "n_bogus")
            assert status == 404


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
