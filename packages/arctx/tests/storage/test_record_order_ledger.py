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
