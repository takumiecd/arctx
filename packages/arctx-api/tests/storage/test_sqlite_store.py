"""Tests for SqliteRunStore round-trip."""

from __future__ import annotations

import tempfile

import pytest

from arctx import init
from arctx.core.append import AppendBatch
from arctx.core.schema.payloads import CutPayload, NodePayload, TransitionPayload
from arctx.core.schema.requirements import Requirement
from arctx.core.schema.work import WorkSession
from arctx.storage.sqlite import SqliteRunStore


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _tp(t_type: str = "experiment") -> TransitionPayload:
    return TransitionPayload(payload_id="_", target_id="_", type=t_type)


def _np() -> NodePayload:
    return NodePayload(payload_id="_", target_id="_", type="note", content={"text": "hi"})


def _make_populated_run(run_id: str = "test_run"):
    run = init(_req(), run_id=run_id)
    t1 = run.transition([run.root_node_id], _tp("suggestion"))
    n1 = t1.output_node_id
    t2 = run.transition([n1], _tp("implementation"))
    run.attach(run.root_node_id, _np())
    return run


def test_round_trip_basic():
    run = _make_populated_run("sq_basic")
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_basic")

    assert loaded.run_id == run.run_id
    assert len(loaded.run_graph.nodes) == len(run.run_graph.nodes)
    assert len(loaded.run_graph.transitions) == len(run.run_graph.transitions)
    assert len(loaded.run_graph.payloads) == len(run.run_graph.payloads)


def test_round_trip_indices_rebuilt():
    run = _make_populated_run("sq_idx")
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_idx")

    for tid, t in loaded.run_graph.transitions.items():
        for nid in t.input_node_ids:
            assert tid in loaded.run_graph.transitions_by_input_node.get(nid, [])
        if t.output_node_id:
            assert loaded.run_graph.transition_by_output_node.get(t.output_node_id) == tid


def test_round_trip_payloads_preserved():
    run = _make_populated_run("sq_payloads")
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_payloads")

    assert len(loaded.run_graph.payloads) == len(run.run_graph.payloads)


def test_round_trip_with_cut():
    run = _make_populated_run("sq_cut")
    t_ids = list(run.run_graph.transitions)
    run.cut(t_ids[0], target_kind="transition", reason="bad")
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_cut")

    cut_payloads = [p for p in loaded.run_graph.payloads.values() if isinstance(p, CutPayload)]
    assert len(cut_payloads) >= 1


def test_round_trip_views_preserved():
    run = _make_populated_run("sq_views")
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_views")

    assert "main" in loaded.run_graph.views


def test_list_runs():
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        run1 = _make_populated_run("sq_a")
        run2 = _make_populated_run("sq_b")
        store.save_run(run1)
        store.save_run(run2)
        listed = store.list_runs()
        ids = [r["run_id"] for r in listed]
        assert "sq_a" in ids
        assert "sq_b" in ids


def test_append_batch_rejects_work_session_user_mismatch():
    run = init(_req(), run_id="sq_ws_conflict")
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        store.append_batch(
            AppendBatch(
                run_id=run.run_id,
                user_id="user_a",
                work_session_id="ws_shared",
                work_session=WorkSession("ws_shared", run.run_id, "user_a"),
                records=(),
                events=(),
            )
        )

        with pytest.raises(ValueError, match="belongs to user"):
            store.append_batch(
                AppendBatch(
                    run_id=run.run_id,
                    user_id="user_b",
                    work_session_id="ws_shared",
                    work_session=WorkSession("ws_shared", run.run_id, "user_b"),
                    records=(),
                    events=(),
                )
            )
