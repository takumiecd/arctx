"""Lane DAG and collapsed LanePayload overview semantics."""

from __future__ import annotations

import pytest

import arctx
from arctx.core.lanes import lane_links, lane_overview, lane_roots
from arctx.core.run.export import ExportOptions, json_document
from arctx.core.schema.payloads import LanePayload
from arctx.core.schema.requirements import Requirement
from arctx.storage.jsonl import JsonlRunStore
from arctx.storage.sqlite import SqliteRunStore


def _handle():
    return arctx.init(
        Requirement(requirement_id="r", target_type="task", target_id="t"),
        run_id="run_lane_overview",
    )


def _attach(handle, lane_id: str, type: str, text: str):
    return handle.attach_lane(
        lane_id,
        LanePayload(
            payload_id=handle._next_id("pl"),
            target_id=lane_id,
            type=type,
            content={"text": text},
        ),
        user_id="alice",
    )


def test_overview_uses_latest_current_values_and_accumulates_collections():
    handle = _handle()
    handle.ensure_lane(name="auth", lane_id="lane_auth", created_by="alice")
    first = _attach(handle, "lane_auth", "summary", "comparing options")
    _attach(handle, "lane_auth", "purpose", "choose authentication")
    _attach(handle, "lane_auth", "question", "where are keys stored?")
    latest = _attach(handle, "lane_auth", "summary", "PKCE is currently preferred")

    overview = lane_overview(handle.run_graph, "lane_auth")

    assert overview.summary == latest
    assert overview.summary != first
    assert overview.purpose.content["text"] == "choose authentication"
    assert [p.content["text"] for p in overview.collections["question"]] == [
        "where are keys stored?"
    ]


def test_lane_links_form_a_multi_parent_dag_and_reject_cycles():
    handle = _handle()
    for lane_id in ("lane_a", "lane_b", "lane_shared"):
        handle.ensure_lane(name=lane_id, lane_id=lane_id, created_by="alice")
        _attach(handle, lane_id, "summary", f"summary for {lane_id}")

    handle.link_lanes("lane_a", "lane_shared", user_id="alice")
    handle.link_lanes("lane_b", "lane_shared", user_id="alice")

    assert {(link.parent_lane_id, link.child_lane_id) for link in lane_links(handle.run_graph)} == {
        ("lane_a", "lane_shared"),
        ("lane_b", "lane_shared"),
    }
    assert lane_roots(handle.run_graph) == ("lane_a", "lane_b")
    assert set(lane_overview(handle.run_graph, "lane_shared").parent_lane_ids) == {
        "lane_a",
        "lane_b",
    }
    with pytest.raises(ValueError, match="cycle"):
        handle.link_lanes("lane_shared", "lane_a", user_id="alice")


def test_parent_overview_becomes_fresh_after_summary_update():
    handle = _handle()
    handle.ensure_lane(name="parent", lane_id="lane_parent", created_by="alice")
    handle.ensure_lane(name="child", lane_id="lane_child", created_by="alice")
    _attach(handle, "lane_parent", "summary", "initial parent view")
    _attach(handle, "lane_child", "summary", "new child finding")
    handle.link_lanes("lane_parent", "lane_child", user_id="alice")

    assert lane_overview(handle.run_graph, "lane_parent").stale_child_lane_ids == (
        "lane_child",
    )

    _attach(handle, "lane_parent", "summary", "parent incorporates child finding")
    assert lane_overview(handle.run_graph, "lane_parent").stale_child_lane_ids == ()


@pytest.mark.parametrize("store_cls", [JsonlRunStore, SqliteRunStore])
def test_lane_payloads_and_dag_roundtrip_storage(tmp_path, store_cls):
    handle = _handle()
    handle.ensure_lane(name="parent", lane_id="lane_parent", created_by="alice")
    handle.ensure_lane(name="child", lane_id="lane_child", created_by="alice")
    _attach(handle, "lane_parent", "summary", "parent summary")
    _attach(handle, "lane_child", "summary", "child summary")
    handle.link_lanes("lane_parent", "lane_child", user_id="alice")

    store = store_cls(tmp_path / store_cls.__name__)
    store.save_run(handle)
    loaded = store.load_run(handle.run_id)

    assert (
        lane_overview(loaded.run_graph, "lane_parent").summary.content["text"]
        == "parent summary"
    )
    assert lane_overview(loaded.run_graph, "lane_parent").child_lane_ids == (
        "lane_child",
    )
    assert loaded.run_graph.payloads_for_lane("lane_child")[0].target_kind == "lane"


def test_json_export_includes_lane_payloads_links_and_overviews():
    handle = _handle()
    handle.ensure_lane(name="parent", lane_id="lane_parent", created_by="alice")
    handle.ensure_lane(name="child", lane_id="lane_child", created_by="alice")
    summary = _attach(handle, "lane_parent", "summary", "parent summary")
    _attach(handle, "lane_child", "summary", "child summary")
    handle.link_lanes("lane_parent", "lane_child", user_id="alice")

    document = json_document(handle, ExportOptions())

    assert any(payload["payload_id"] == summary.payload_id for payload in document["payloads"])
    assert document["lane_links"][0]["child_lane_id"] == "lane_child"
    assert document["lane_overviews"][0]["lane_id"] == "lane_parent"
