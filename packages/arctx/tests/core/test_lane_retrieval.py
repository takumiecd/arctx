"""Tests for flat lane retrieval: overviews, current summary, and search.

Retrieval is the read half of the git-native model. Lanes are flat, so these
helpers never walk a hierarchy — ordering comes from the append-only work-event
log and search is position-independent.
"""

from __future__ import annotations

import pytest

import arctx
from arctx.core.lanes import (
    collapse_summary,
    lane_current_summary,
    lane_overview,
    lane_purpose,
    lane_summary_payloads,
    list_lane_overviews,
    record_event_rank,
    search_lanes,
)
from arctx.core.schema.payloads import StepPayload, SummaryPayload
from arctx.core.schema.requirements import Requirement


def _handle(run_id: str = "run_retrieval"):
    return arctx.init(
        Requirement(requirement_id="r", target_type="task", target_id="t"),
        run_id=run_id,
    )


def _step(handle, from_node: str, lane_id: str, note: str) -> str:
    step = handle.add_step(
        input_node_ids=[from_node],
        payload=StepPayload(
            payload_id=handle._next_id("pl"),
            target_id="pending",
            type="experiment",
            content={"note": note},
        ),
        user_id="alice",
        lane_id=lane_id,
    )
    return step.output_node_id


def _summarize(handle, node_id: str, lane_id: str, text: str) -> SummaryPayload:
    # ``attach`` mints a fresh payload id, so return what it stored.
    return handle.attach(
        node_id,
        SummaryPayload(payload_id="pending", target_id=node_id, text=text),
        user_id="alice",
        lane_id=lane_id,
    )


@pytest.fixture()
def seeded():
    """One handle with lanes 'tiling' (open) and 'warp' (closed)."""
    h = _handle()
    h.ensure_lane(
        name="tiling",
        lane_id="lane_tiling",
        created_by="alice",
        metadata={"purpose": "try shared-memory tiling"},
    )
    h.ensure_lane(name="warp", lane_id="lane_warp", created_by="alice")

    baseline = _step(h, h.root_node_id, "lane_tiling", "baseline kernel 12ms")
    tiled = _step(h, baseline, "lane_tiling", "tiling 32x32 gives 4ms")
    _summarize(h, tiled, "lane_tiling", "32x32 tiling wins.\nOccupancy detail.")

    warp_node = _step(h, baseline, "lane_warp", "warp shuffle slower, 15ms")
    _summarize(h, warp_node, "lane_warp", "Warp shuffle regressed; abandoned.")
    h.set_lane_status("lane_warp", status="closed", user_id="alice")
    return h


# ---------------------------------------------------------------------------
# summary ordering
# ---------------------------------------------------------------------------


def test_record_event_rank_follows_the_work_event_log():
    h = _handle()
    h.ensure_lane(name="a", lane_id="lane_a", created_by="alice")
    first = _step(h, h.root_node_id, "lane_a", "one")
    second = _step(h, first, "lane_a", "two")
    rank = record_event_rank(h.run_graph)
    assert rank[first] < rank[second]


def test_lane_current_summary_is_the_latest_one(seeded):
    node = lane_overview(seeded.run_graph, "lane_tiling").summary_node_id
    later = _summarize(seeded, node, "lane_tiling", "Revised: 3.5ms after unrolling.")

    ordered = lane_summary_payloads(seeded.run_graph, "lane_tiling")
    assert len(ordered) == 2
    assert ordered[-1].payload_id == later.payload_id

    current = lane_current_summary(seeded.run_graph, "lane_tiling")
    assert current is not None
    assert current.text.startswith("Revised:")


def test_lane_without_summary_reports_none(seeded):
    seeded.ensure_lane(name="fresh", lane_id="lane_fresh", created_by="alice")
    assert lane_current_summary(seeded.run_graph, "lane_fresh") is None


def test_summaries_do_not_leak_between_lanes(seeded):
    tiling = lane_current_summary(seeded.run_graph, "lane_tiling")
    warp = lane_current_summary(seeded.run_graph, "lane_warp")
    assert tiling is not None and warp is not None
    assert tiling.payload_id != warp.payload_id
    assert "tiling" in tiling.text
    assert "Warp" in warp.text


# ---------------------------------------------------------------------------
# collapse / purpose
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  \n\nfirst line\nsecond", "first line"),
        ("only", "only"),
    ],
)
def test_collapse_summary_takes_the_first_non_empty_line(text, expected):
    assert collapse_summary(text) == expected


def test_collapse_summary_truncates_to_the_limit():
    collapsed = collapse_summary("y" * 500)
    assert len(collapsed) == 160
    assert collapsed.endswith("...")


def test_lane_purpose_reads_metadata(seeded):
    assert lane_purpose(seeded.run_graph.lanes["lane_tiling"]) == (
        "try shared-memory tiling"
    )
    assert lane_purpose(seeded.run_graph.lanes["lane_warp"]) is None


# ---------------------------------------------------------------------------
# overviews
# ---------------------------------------------------------------------------


def test_lane_overview_counts_and_frontiers(seeded):
    overview = lane_overview(
        seeded.run_graph, "lane_tiling", root_node_id=seeded.root_node_id
    )
    assert overview.label == "tiling"
    assert overview.status == "open"
    assert overview.purpose == "try shared-memory tiling"
    assert overview.node_count == 2
    assert overview.step_count == 2
    assert overview.summary_line == "32x32 tiling wins."
    assert overview.summary_text is not None
    assert "Occupancy detail." in overview.summary_text
    assert overview.active_frontier_node_ids


def test_lane_overview_unknown_lane_raises(seeded):
    with pytest.raises(KeyError):
        lane_overview(seeded.run_graph, "lane_nope")


def test_list_lane_overviews_puts_open_lanes_first(seeded):
    overviews = list_lane_overviews(
        seeded.run_graph, root_node_id=seeded.root_node_id
    )
    statuses = [item.status for item in overviews]
    assert statuses == sorted(statuses, key=lambda s: s != "open")
    assert overviews[0].label == "tiling"
    assert overviews[-1].label == "warp"


def test_lane_overview_to_dict_has_no_hierarchy_keys(seeded):
    data = lane_overview(seeded.run_graph, "lane_tiling").to_dict()
    for gone in (
        "parent_lane_id",
        "child_lane_ids",
        "breadcrumb",
        "ancestors",
        "stale_child_lane_ids",
    ):
        assert gone not in data


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_matches_payload_content(seeded):
    hits = search_lanes(seeded.run_graph, "15ms", root_node_id=seeded.root_node_id)
    assert [hit.lane_id for hit in hits] == ["lane_warp"]
    assert "15ms" in hits[0].snippet
    assert hits[0].matched_payload_ids
    assert hits[0].matched_record_ids


def test_search_matches_lane_name_and_ranks_it_first(seeded):
    # "warp" appears in the warp lane's name and in the tiling lane's own
    # payload text only if we add it there.
    node = lane_overview(seeded.run_graph, "lane_tiling").summary_node_id
    _summarize(seeded, node, "lane_tiling", "Compared against the warp variant.")

    hits = search_lanes(seeded.run_graph, "warp", root_node_id=seeded.root_node_id)
    assert [hit.lane_id for hit in hits] == ["lane_warp", "lane_tiling"]
    assert hits[0].name_match is True
    assert hits[1].name_match is False


def test_search_terms_are_and_matched(seeded):
    assert search_lanes(seeded.run_graph, "warp shuffle")
    assert search_lanes(seeded.run_graph, "warp occupancy") == ()


def test_search_is_case_insensitive(seeded):
    assert search_lanes(seeded.run_graph, "ABANDONED")


def test_search_matches_lane_purpose(seeded):
    hits = search_lanes(seeded.run_graph, "shared-memory")
    assert [hit.lane_id for hit in hits] == ["lane_tiling"]


def test_search_finds_closed_lanes(seeded):
    hits = search_lanes(seeded.run_graph, "abandoned")
    assert [hit.status for hit in hits] == ["closed"]


def test_empty_query_returns_nothing(seeded):
    assert search_lanes(seeded.run_graph, "") == ()
    assert search_lanes(seeded.run_graph, "   ") == ()


def test_search_snippet_omits_opaque_ids(seeded):
    hits = search_lanes(seeded.run_graph, "15ms")
    snippet = hits[0].snippet
    assert "pl_" not in snippet
    assert "n_" not in snippet
    assert "t_" not in snippet


def test_search_hit_to_dict_has_no_breadcrumb(seeded):
    data = search_lanes(seeded.run_graph, "15ms")[0].to_dict()
    assert "breadcrumb" not in data
    assert data["matched_payload_ids"]
