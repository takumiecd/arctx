"""Tests for ``arctx explore`` — the flat, summary-first retrieval surface.

Covers the three modes (flat list / one lane / search), closed-lane folding,
and search ranking. Lanes are flat here: nothing in these tests descends a
hierarchy, because there is none.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.explore import render_explore, run_explore_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import (
    run_lane_close_command,
    run_lane_create_command,
    run_lane_summarize_command,
)
from arctx_cli.context import resolve_store

RUN_ID = "run_explore"


def _store_dir(tmp_path: Path) -> str:
    return str(tmp_path / "runs")


def _init(tmp_path: Path) -> str:
    sd = _store_dir(tmp_path)
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id=RUN_ID,
        store_dir=sd,
    )
    return sd


def _root(sd: str) -> str:
    return resolve_store(sd).load_run(RUN_ID).root_node_id


def _add(sd: str, from_node: str, lane_id: str, note: str) -> str:
    res = run_add_step_command(
        run_id=RUN_ID,
        input_node_ids=[from_node],
        title=note,
        payload_kind="experiment",
        payload_type="step_payload",
        field_data={"note": note},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id=lane_id,
    )
    return res["step"]["output_node_id"]


@pytest.fixture()
def run_with_lanes(tmp_path):
    """Two lanes: 'tiling' (open, summarized) and 'warp' (closed)."""
    sd = _init(tmp_path)
    tiling = run_lane_create_command(
        name="tiling",
        run_id=RUN_ID,
        user_id="alice",
        store_dir=sd,
        purpose="try shared-memory tiling",
    )["lane_id"]
    baseline = _add(sd, _root(sd), tiling, "baseline kernel 12ms")
    _add(sd, baseline, tiling, "tiling 32x32 gives 4ms")
    run_lane_summarize_command(
        name_or_id="tiling",
        summary="32x32 tiling wins: 12ms -> 4ms.\nOccupancy tradeoff detail.",
        node_ids=None,
        run_id=RUN_ID,
        user_id="alice",
        store_dir=sd,
    )

    warp = run_lane_create_command(
        name="warp",
        run_id=RUN_ID,
        user_id="alice",
        store_dir=sd,
        purpose="warp shuffle reduction",
    )["lane_id"]
    _add(sd, baseline, warp, "warp shuffle slower, 15ms")
    run_lane_close_command(
        name_or_id="warp",
        summary="Warp shuffle regressed to 15ms; abandoned.",
        node_ids=None,
        reason=None,
        run_id=RUN_ID,
        user_id="alice",
        store_dir=sd,
    )
    return sd


# ---------------------------------------------------------------------------
# flat list
# ---------------------------------------------------------------------------


def test_flat_list_shows_open_lanes_and_folds_closed(run_with_lanes):
    result = run_explore_command(run_id=RUN_ID, store_dir=run_with_lanes)
    assert result["mode"] == "list"
    assert [lane["label"] for lane in result["lanes"]] == ["tiling"]
    assert result["hidden_closed"] == 1
    assert result["total"] == 2

    text = render_explore(result)
    assert "* tiling" in text
    assert "1 closed lane — use --all" in text
    assert "warp" not in text


def test_flat_list_all_includes_closed_lanes_last(run_with_lanes):
    result = run_explore_command(run_id=RUN_ID, store_dir=run_with_lanes, show_all=True)
    assert [lane["label"] for lane in result["lanes"]] == ["tiling", "warp"]
    assert result["hidden_closed"] == 0
    text = render_explore(result)
    assert "- warp" in text


def test_flat_list_collapses_summary_to_one_line(run_with_lanes):
    result = run_explore_command(run_id=RUN_ID, store_dir=run_with_lanes)
    lane = result["lanes"][0]
    assert lane["summary_line"] == "32x32 tiling wins: 12ms -> 4ms."
    assert "Occupancy tradeoff detail." not in render_explore(result)


def test_flat_list_truncates_long_summary_lines(tmp_path):
    sd = _init(tmp_path)
    lane_id = run_lane_create_command(
        name="long", run_id=RUN_ID, user_id="alice", store_dir=sd
    )["lane_id"]
    _add(sd, _root(sd), lane_id, "work")
    run_lane_summarize_command(
        name_or_id="long",
        summary="x" * 400,
        node_ids=None,
        run_id=RUN_ID,
        user_id="alice",
        store_dir=sd,
    )
    lane = run_explore_command(run_id=RUN_ID, store_dir=sd)["lanes"][0]
    assert len(lane["summary_line"]) == 160
    assert lane["summary_line"].endswith("...")


def test_flat_list_on_empty_run(tmp_path):
    sd = _init(tmp_path)
    result = run_explore_command(run_id=RUN_ID, store_dir=sd)
    assert result["lanes"] == []
    assert render_explore(result) == "(no lanes)"


# ---------------------------------------------------------------------------
# single lane
# ---------------------------------------------------------------------------


def test_single_lane_overview_by_name(run_with_lanes):
    result = run_explore_command(
        run_id=RUN_ID, store_dir=run_with_lanes, lane_name_or_id="tiling"
    )
    lane = result["lane"]
    assert result["mode"] == "lane"
    assert lane["status"] == "open"
    assert lane["purpose"] == "try shared-memory tiling"
    # The full summary, not the collapsed line.
    assert "Occupancy tradeoff detail." in lane["summary"]
    assert lane["counts"]["nodes"] == 2
    assert lane["counts"]["steps"] == 2
    assert lane["active_frontier_node_ids"]

    text = render_explore(result)
    assert "purpose: try shared-memory tiling" in text
    assert "Occupancy tradeoff detail." in text
    assert "active frontiers:" in text


def test_single_lane_overview_by_id(run_with_lanes):
    by_name = run_explore_command(
        run_id=RUN_ID, store_dir=run_with_lanes, lane_name_or_id="tiling"
    )
    by_id = run_explore_command(
        run_id=RUN_ID,
        store_dir=run_with_lanes,
        lane_name_or_id=by_name["lane"]["lane_id"],
    )
    assert by_id == by_name


def test_single_lane_unknown_raises(run_with_lanes):
    with pytest.raises(KeyError):
        run_explore_command(
            run_id=RUN_ID, store_dir=run_with_lanes, lane_name_or_id="nope"
        )


def test_lane_without_purpose_or_summary_renders_placeholders(tmp_path):
    sd = _init(tmp_path)
    run_lane_create_command(name="bare", run_id=RUN_ID, user_id="alice", store_dir=sd)
    result = run_explore_command(run_id=RUN_ID, store_dir=sd, lane_name_or_id="bare")
    assert result["lane"]["purpose"] is None
    assert result["lane"]["summary"] is None
    text = render_explore(result)
    assert "purpose: (not recorded)" in text
    assert "summary: (none yet)" in text


# ---------------------------------------------------------------------------
# search — the primary retrieval path
# ---------------------------------------------------------------------------


def test_query_matches_lane_payload_text(run_with_lanes):
    result = run_explore_command(
        run_id=RUN_ID, store_dir=run_with_lanes, query="15ms"
    )
    assert result["mode"] == "search"
    assert [hit["label"] for hit in result["matches"]] == ["warp"]
    hit = result["matches"][0]
    assert "15ms" in hit["snippet"]
    assert hit["status"] == "closed"
    # Jump targets so the caller can `arctx show` without another search.
    assert hit["matched_payload_ids"]
    assert hit["matched_record_ids"]


def test_query_finds_closed_lanes_without_all_flag(run_with_lanes):
    """Search is position-independent: closed lanes are still findable."""
    result = run_explore_command(
        run_id=RUN_ID, store_dir=run_with_lanes, query="abandoned"
    )
    assert [hit["label"] for hit in result["matches"]] == ["warp"]


def test_query_terms_are_and_matched(run_with_lanes):
    both = run_explore_command(
        run_id=RUN_ID, store_dir=run_with_lanes, query="warp shuffle"
    )
    assert [hit["label"] for hit in both["matches"]] == ["warp"]

    neither = run_explore_command(
        run_id=RUN_ID, store_dir=run_with_lanes, query="warp occupancy"
    )
    assert neither["matches"] == []


def test_query_is_case_insensitive(run_with_lanes):
    result = run_explore_command(
        run_id=RUN_ID, store_dir=run_with_lanes, query="ABANDONED"
    )
    assert [hit["label"] for hit in result["matches"]] == ["warp"]


def test_query_ranks_name_matches_first(run_with_lanes):
    """'tiling' matches the tiling lane's name and the warp lane's body text."""
    sd = run_with_lanes
    lane_id = run_lane_create_command(
        name="zzz-other", run_id=RUN_ID, user_id="alice", store_dir=sd
    )["lane_id"]
    root = resolve_store(sd).load_run(RUN_ID)
    baseline = next(
        node_id
        for node_id in root.run_graph.nodes
        if node_id != root.root_node_id
    )
    _add(sd, baseline, lane_id, "compared against tiling numbers")

    result = run_explore_command(run_id=RUN_ID, store_dir=sd, query="tiling")
    labels = [hit["label"] for hit in result["matches"]]
    assert labels[0] == "tiling"
    assert result["matches"][0]["name_match"] is True
    assert "zzz-other" in labels
    assert result["matches"][labels.index("zzz-other")]["name_match"] is False


def test_query_snippet_excludes_opaque_ids(run_with_lanes):
    result = run_explore_command(
        run_id=RUN_ID, store_dir=run_with_lanes, query="15ms"
    )
    snippet = result["matches"][0]["snippet"]
    assert "pl_" not in snippet
    assert "n_" not in snippet
    assert "t_" not in snippet


def test_query_with_no_hits(run_with_lanes):
    result = run_explore_command(
        run_id=RUN_ID, store_dir=run_with_lanes, query="quantization"
    )
    assert result["matches"] == []
    assert render_explore(result) == "(no matching lanes)"


def test_query_takes_precedence_over_lane_argument(run_with_lanes):
    result = run_explore_command(
        run_id=RUN_ID,
        store_dir=run_with_lanes,
        lane_name_or_id="tiling",
        query="15ms",
    )
    assert result["mode"] == "search"
    assert [hit["label"] for hit in result["matches"]] == ["warp"]


def test_unknown_run_raises(tmp_path):
    with pytest.raises(KeyError):
        run_explore_command(run_id="run_missing", store_dir=_store_dir(tmp_path))
