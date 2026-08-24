"""The same committed bytes must answer the same way on every machine.

Read order comes from the work-event ledger. Anything that wrote a record
without an event left it unranked, and an unranked record used to sort ahead
of the entire ledger -- so a record written *last* was re-read as the
*oldest*. For cut/uncut, where the last marker wins, that inverted the answer:
the writer's warm cache said cut, a fresh clone said active.
"""

from __future__ import annotations

import json

import pytest

from arctx import init
from arctx.core.cuts import is_active_node
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.storage.jsonl import JsonlRunStore, _ordered_rows


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _run_with_cli_cut_then_uncut(store: JsonlRunStore):
    handle = init(_req(), run_id="ord")
    handle.ensure_lane(user_id="u", lane_id="L1")
    step = handle.add_step(
        [handle.root_node_id],
        StepPayload(payload_id="_", target_id="_", type="note"),
        user_id="u",
        lane_id="L1",
    )
    node_id = step.output_node_id
    handle.cut(node_id, target_kind="node", reason="cli cut", user_id="u", lane_id="L1")
    handle.uncut(node_id, target_kind="node", reason="cli uncut", user_id="u", lane_id="L1")
    store.save_run(handle)
    return node_id


def test_a_late_library_cut_survives_a_cold_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    store = JsonlRunStore(str(tmp_path / "runs"))
    node_id = _run_with_cli_cut_then_uncut(store)

    # The documented core API, with no user/lane -- the write that used to
    # vanish. It is the last marker, so the node is cut.
    handle = store.load_run("ord")
    handle.cut(node_id, target_kind="node", reason="library cut")
    store.save_run(handle)
    assert is_active_node(handle.run_graph, node_id) is False

    # A different machine: different cache root, nothing warm.
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "other-machine"))
    fresh = JsonlRunStore(str(tmp_path / "runs")).load_run("ord")
    assert is_active_node(fresh.run_graph, node_id) is False


def test_save_run_numbers_every_work_event(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    store = JsonlRunStore(str(tmp_path / "runs"))
    node_id = _run_with_cli_cut_then_uncut(store)
    handle = store.load_run("ord")
    handle.cut(node_id, target_kind="node", reason="library cut")
    store.save_run(handle)

    seqs = [
        json.loads(line)["seq"]
        for line in (tmp_path / "runs" / "ord" / "work_events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert None not in seqs, "a null seq sorts ahead of the whole ledger"
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))


def test_unranked_rows_anchor_where_they_were_written():
    rank = {"a": 0, "b": 1, "c": 2}
    rows = [{"i": "a"}, {"i": "b"}, {"i": "c"}, {"i": "late"}]
    assert [r["i"] for r in _ordered_rows(rows, "i", rank)] == ["a", "b", "c", "late"]


def test_bootstrap_rows_stay_ahead_of_the_ledger():
    rank = {"a": 0, "b": 1}
    rows = [{"i": "root"}, {"i": "a"}, {"i": "b"}]
    assert [r["i"] for r in _ordered_rows(rows, "i", rank)] == ["root", "a", "b"]


def test_scrambled_file_order_falls_back_to_rank_alone():
    """A union merge interleaves lines, so file order carries no information."""
    rank = {"a": 0, "b": 1, "c": 2}
    rows = [{"i": "c"}, {"i": "a"}, {"i": "b"}]  # not ascending by rank
    assert [r["i"] for r in _ordered_rows(rows, "i", rank)] == ["a", "b", "c"]


def test_a_run_with_no_ledger_keeps_file_order():
    rows = [{"i": "x"}, {"i": "y"}, {"i": "z"}]
    assert [r["i"] for r in _ordered_rows(rows, "i", {})] == ["x", "y", "z"]


@pytest.mark.parametrize("marker", ["cut", "uncut"])
def test_pure_library_runs_still_record_no_events(tmp_path, monkeypatch, marker):
    """The library-only caller who never passes a user/lane keeps file order."""
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    handle = init(_req(), run_id="lib")
    step = handle.add_step(
        [handle.root_node_id], StepPayload(payload_id="_", target_id="_", type="note")
    )
    handle.cut(step.output_node_id, target_kind="node")
    if marker == "uncut":
        handle.uncut(step.output_node_id, target_kind="node")

    assert handle.run_graph.work_events == []
    assert is_active_node(handle.run_graph, step.output_node_id) is (marker == "uncut")


# ---------------------------------------------------------------------------
# event order across a union merge
# ---------------------------------------------------------------------------


def test_events_order_by_time_not_by_seq():
    """`seq` is per-file and dense, so it collides across a union merge.

    Two branches each number their events from the same place, and a branch
    that did more work carries higher numbers regardless of when it did them.
    Ordering by seq first made the merged cut/uncut state depend on which
    branch appended more events rather than on which decision came last.
    """
    from arctx.storage.jsonl import _sort_event_rows

    rows = [
        # the branch that did more work: high seq, but it acted FIRST
        {"event_id": "e_a", "seq": 10, "created_at": "2026-08-24T01:00:00Z"},
        # the branch that acted LAST: low seq
        {"event_id": "e_b", "seq": 4, "created_at": "2026-08-24T02:00:00Z"},
    ]
    assert [r["event_id"] for r in _sort_event_rows(rows)] == ["e_a", "e_b"]


def test_seq_still_breaks_ties_inside_one_timestamp():
    from arctx.storage.jsonl import _sort_event_rows

    rows = [
        {"event_id": "e_2", "seq": 2, "created_at": "2026-08-24T01:00:00Z"},
        {"event_id": "e_1", "seq": 1, "created_at": "2026-08-24T01:00:00Z"},
    ]
    assert [r["event_id"] for r in _sort_event_rows(rows)] == ["e_1", "e_2"]


def test_core_event_order_agrees_with_storage():
    """The two orderings are mirrors; drift between them is a silent bug."""
    from arctx.core.lanes import _event_order
    from arctx.core.schema.work import WorkEvent

    def ev(event_id, seq, created_at):
        return WorkEvent(
            event_id=event_id,
            run_id="r",
            lane_id="L",
            user_id="u",
            event_type="cut_added",
            seq=seq,
            created_at=created_at,
        )

    earlier = ev("e_a", 10, "2026-08-24T01:00:00Z")
    later = ev("e_b", 4, "2026-08-24T02:00:00Z")
    assert _event_order(later) > _event_order(earlier)
