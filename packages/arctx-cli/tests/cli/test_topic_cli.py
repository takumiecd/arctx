"""Tests for `arctx topic` / `arctx topics`."""

from __future__ import annotations

from pathlib import Path

import pytest

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.topic import (
    run_topic_join_command,
    run_topic_split_command,
    run_topic_summarize_command,
    run_topic_tag_command,
    run_topic_untag_command,
    split_notice,
)
from arctx_cli.context import resolve_store

from arctx.core.topics import topic_view


def _store_dir(td) -> str:
    return str(Path(td) / "runs")


def _init(td) -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="run_topic",
        store_dir=_store_dir(td),
    )


def _add(td, from_node, title="work") -> dict:
    return run_add_step_command(
        run_id="run_topic",
        input_node_ids=[from_node],
        title=title,
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=_store_dir(td),
    )["step"]


def _graph(td):
    return resolve_store(_store_dir(td)).load_run("run_topic").run_graph


def test_tag_records_and_view_islands(tmp_path):
    init = _init(tmp_path)
    a = _add(tmp_path, init["root_node_id"])
    b = _add(tmp_path, init["root_node_id"])

    result = run_topic_tag_command(
        run_id="run_topic",
        name="gather",
        record_ids=[a["output_node_id"], b["id"]],
        note="promising",
        store_dir=_store_dir(tmp_path),
    )
    assert result["tagged"] == [a["output_node_id"], b["id"]]

    view = topic_view(_graph(tmp_path), "gather")
    assert {r.record_id for r in view.records} == {a["output_node_id"], b["id"]}
    assert {r.kind for r in view.records} == {"node", "step"}
    # Sibling branches share an ancestor but neither derives from the other:
    # two islands — the join-candidate signal.
    assert len(view.islands) == 2


def test_tag_unknown_record_is_rejected(tmp_path):
    _init(tmp_path)
    with pytest.raises(KeyError):
        run_topic_tag_command(
            run_id="run_topic",
            name="gather",
            record_ids=["n_missing"],
            note=None,
            store_dir=_store_dir(tmp_path),
        )


def test_summarize_latest_wins_and_sources_checked(tmp_path):
    init = _init(tmp_path)
    a = _add(tmp_path, init["root_node_id"])

    run_topic_summarize_command(
        run_id="run_topic",
        name="tile",
        text="old belief",
        sources=None,
        on_node=a["output_node_id"],
        store_dir=_store_dir(tmp_path),
    )
    run_topic_summarize_command(
        run_id="run_topic",
        name="tile",
        text="new belief",
        sources=[a["id"]],
        on_node=a["output_node_id"],
        store_dir=_store_dir(tmp_path),
    )
    view = topic_view(_graph(tmp_path), "tile")
    assert view.summary.text == "new belief"
    assert view.summary.sources == (a["id"],)

    with pytest.raises(KeyError, match="unknown --source"):
        run_topic_summarize_command(
            run_id="run_topic",
            name="tile",
            text="x",
            sources=["n_nope"],
            on_node=a["output_node_id"],
            store_dir=_store_dir(tmp_path),
        )


def test_tag_attributes_to_the_tagged_records_own_lane(tmp_path):
    """Without --lane, a tag lands in the lane that owns the tagged record —
    tagging while browsing needs no lane switch and no bookkeeping lane."""
    from arctx.core.lanes import lane_membership
    from arctx_cli.commands.lane import run_lane_close_command, run_lane_create_command

    init = _init(tmp_path)
    lane = run_lane_create_command(
        name="research", run_id="run_topic", user_id="u", store_dir=_store_dir(tmp_path)
    )
    ambient = run_lane_create_command(
        name="ambient", run_id="run_topic", user_id="u", store_dir=_store_dir(tmp_path)
    )
    step = run_add_step_command(
        run_id="run_topic", input_node_ids=[init["root_node_id"]], title="work",
        payload_kind=None, payload_type="step_payload", field_data={}, json_data={},
        store_dir=_store_dir(tmp_path), user_id="u", lane_id=lane["lane_id"],
    )["step"]

    result = run_topic_tag_command(
        run_id="run_topic", name="gather", record_ids=[step["id"]], note=None,
        store_dir=_store_dir(tmp_path), user_id="u",
        lane_id=None, fallback_lane_id=ambient["lane_id"],
    )
    graph = _graph(tmp_path)
    membership = lane_membership(graph)
    tag_payload_id = result["payloads"][0]["payload"]["payload_id"]
    assert membership.payload_to_lane[tag_payload_id] == lane["lane_id"]

    # Once the record's lane closes, attribution falls back to the ambient lane.
    run_lane_close_command(
        name_or_id="research", summary="done", node_ids=None, reason=None,
        run_id="run_topic", user_id="u", store_dir=_store_dir(tmp_path),
    )
    result = run_topic_tag_command(
        run_id="run_topic", name="gather2", record_ids=[step["id"]], note=None,
        store_dir=_store_dir(tmp_path), user_id="u",
        lane_id=None, fallback_lane_id=ambient["lane_id"],
    )
    graph = _graph(tmp_path)
    membership = lane_membership(graph)
    tag_payload_id = result["payloads"][0]["payload"]["payload_id"]
    assert membership.payload_to_lane[tag_payload_id] == ambient["lane_id"]


# ---------------------------------------------------------------------------
# The four resolutions of a split subject
# ---------------------------------------------------------------------------


def _two_islands(tmp_path, name="tiling"):
    """A topic tagged across two sibling lineages — the split signal."""
    init = _init(tmp_path)
    root = init["root_node_id"]
    a = _add(tmp_path, root, "tile sweep")["output_node_id"]
    a2 = _add(tmp_path, a, "32 が最速")["output_node_id"]
    b = _add(tmp_path, root, "CSC に切り替え")["output_node_id"]
    run_topic_tag_command(
        run_id="run_topic",
        name=name,
        record_ids=[a, a2, b],
        note=None,
        store_dir=_store_dir(tmp_path),
    )
    return {"root": root, "a": a, "a2": a2, "b": b}


def test_join_merges_islands_and_records_the_verdict(tmp_path):
    ids = _two_islands(tmp_path)
    assert len(topic_view(_graph(tmp_path), "tiling").islands) == 2

    result = run_topic_join_command(
        run_id="run_topic",
        name="tiling",
        summary="CSR は 32、CSC は 64。境界は format 依存。",
        title=None,
        input_node_ids=None,
        store_dir=_store_dir(tmp_path),
    )

    assert result["islands"] == 1
    # The join takes each island's tip, not any older member.
    assert set(result["joined"]) == {ids["a2"], ids["b"]}

    view = topic_view(_graph(tmp_path), "tiling")
    verdict_node = result["step"]["output_node_id"]
    # The verdict is the statement, and it lives on the node the join produced —
    # a join has no "correct input", only a new record that comes after both.
    assert view.summary.text.startswith("CSR は 32")
    assert view.summary.target_id == verdict_node
    assert set(view.summary.sources) == {ids["a2"], ids["b"]}
    assert verdict_node in {r.record_id for r in view.records}


def test_join_refuses_without_a_verdict_or_when_already_joined(tmp_path):
    _two_islands(tmp_path)
    with pytest.raises(ValueError, match="needs --summary"):
        run_topic_join_command(
            run_id="run_topic", name="tiling", summary="  ", title=None,
            input_node_ids=None, store_dir=_store_dir(tmp_path),
        )
    run_topic_join_command(
        run_id="run_topic", name="tiling", summary="verdict", title=None,
        input_node_ids=None, store_dir=_store_dir(tmp_path),
    )
    with pytest.raises(ValueError, match="already has 1 island"):
        run_topic_join_command(
            run_id="run_topic", name="tiling", summary="again", title=None,
            input_node_ids=None, store_dir=_store_dir(tmp_path),
        )


def test_split_moves_an_island_to_its_own_topic(tmp_path):
    ids = _two_islands(tmp_path)

    result = run_topic_split_command(
        run_id="run_topic",
        name="tiling",
        islands=[2],
        into="csc-tiling",
        summary="CSC の tiling は別 subject",
        store_dir=_store_dir(tmp_path),
    )

    assert result["moved"] == [ids["b"]]
    # Both sides come out with one island each — the signal resolves for both.
    assert result["islands"] == 1
    assert result["into_islands"] == 1

    graph = _graph(tmp_path)
    old = topic_view(graph, "tiling")
    new = topic_view(graph, "csc-tiling")
    assert {r.record_id for r in old.records} == {ids["a"], ids["a2"]}
    assert {r.record_id for r in new.records} == {ids["b"]}
    assert new.summary.text == "CSC の tiling は別 subject"


def test_split_rejects_bad_arguments(tmp_path):
    _two_islands(tmp_path)
    common = dict(run_id="run_topic", name="tiling", store_dir=_store_dir(tmp_path))
    with pytest.raises(ValueError, match="--into"):
        run_topic_split_command(islands=[1], into="", summary="x", **common)
    with pytest.raises(ValueError, match="must differ"):
        run_topic_split_command(islands=[1], into="tiling", summary="x", **common)
    with pytest.raises(ValueError, match="needs --summary"):
        run_topic_split_command(islands=[1], into="other", summary="", **common)
    with pytest.raises(ValueError, match="out of range"):
        run_topic_split_command(islands=[9], into="other", summary="x", **common)


def test_untag_is_reversible_and_leaves_the_record_alone(tmp_path):
    ids = _two_islands(tmp_path)

    run_topic_untag_command(
        run_id="run_topic", name="tiling", record_ids=[ids["b"]],
        store_dir=_store_dir(tmp_path),
    )
    graph = _graph(tmp_path)
    view = topic_view(graph, "tiling")
    assert ids["b"] not in {r.record_id for r in view.records}
    assert len(view.islands) == 1
    assert ids["b"] in graph.nodes  # untag is not cut

    with pytest.raises(ValueError, match="not tagged"):
        run_topic_untag_command(
            run_id="run_topic", name="tiling", record_ids=[ids["b"]],
            store_dir=_store_dir(tmp_path),
        )

    run_topic_tag_command(
        run_id="run_topic", name="tiling", record_ids=[ids["b"]], note=None,
        store_dir=_store_dir(tmp_path),
    )
    assert len(topic_view(_graph(tmp_path), "tiling").islands) == 2


def test_split_notice_offers_every_resolution_as_a_command(tmp_path):
    ids = _two_islands(tmp_path)
    graph = _graph(tmp_path)
    lines = split_notice(graph, topic_view(graph, "tiling"))
    text = "\n".join(lines)

    assert "spans 2 unjoined islands" in lines[0]
    assert "arctx topic join tiling" in text
    assert "arctx topic split tiling --island 2" in text
    assert f"arctx cut {ids['b']}" in text
    assert f"arctx topic untag tiling {ids['b']}" in text
    # A one-island topic says nothing at all.
    run_topic_untag_command(
        run_id="run_topic", name="tiling", record_ids=[ids["b"]],
        store_dir=_store_dir(tmp_path),
    )
    graph = _graph(tmp_path)
    assert split_notice(graph, topic_view(graph, "tiling")) == []
