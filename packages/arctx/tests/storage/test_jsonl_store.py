"""Tests for JsonlRunStore round-trip."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx import init
from arctx.core.append import AppendBatch
from arctx.core.schema.payloads import CutPayload, NodePayload, TransitionPayload
from arctx.core.schema.work import WorkSession
from arctx.core.schema.requirements import Requirement
from arctx.storage.jsonl import JsonlRunStore


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
    run = _make_populated_run("rt_basic")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        loaded = store.load_run("rt_basic")

    assert loaded.run_id == run.run_id
    assert len(loaded.run_graph.nodes) == len(run.run_graph.nodes)
    assert len(loaded.run_graph.transitions) == len(run.run_graph.transitions)
    assert len(loaded.run_graph.payloads) == len(run.run_graph.payloads)


def test_round_trip_indices_rebuilt():
    run = _make_populated_run("rt_idx")
    [t1] = list(run.run_graph.transitions.values())[:1]
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        loaded = store.load_run("rt_idx")

    # Verify reverse indices are rebuilt.
    for tid, t in loaded.run_graph.transitions.items():
        for nid in t.input_node_ids:
            assert tid in loaded.run_graph.transitions_by_input_node.get(nid, [])
        if t.output_node_id:
            assert loaded.run_graph.transition_by_output_node.get(t.output_node_id) == tid


def test_round_trip_payloads_preserved():
    run = _make_populated_run("rt_payloads")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        loaded = store.load_run("rt_payloads")

    assert len(loaded.run_graph.payloads) == len(run.run_graph.payloads)
    for payload_id in run.run_graph.payloads:
        assert payload_id in loaded.run_graph.payloads


def test_round_trip_with_cut():
    run = _make_populated_run("rt_cut")
    t_ids = list(run.run_graph.transitions)
    run.cut(t_ids[0], target_kind="transition", reason="bad")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        loaded = store.load_run("rt_cut")

    cut_payloads = [p for p in loaded.run_graph.payloads.values() if isinstance(p, CutPayload)]
    assert len(cut_payloads) >= 1


def test_round_trip_views_preserved():
    run = _make_populated_run("rt_views")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        loaded = store.load_run("rt_views")

    assert "main" in loaded.run_graph.views


def test_jsonl_files_created():
    run = _make_populated_run("rt_files")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        run_path = Path(td) / "rt_files"
        assert (run_path / "run.json").exists()
        assert (run_path / "nodes.jsonl").exists()
        assert (run_path / "transitions.jsonl").exists()
        assert (run_path / "payloads.jsonl").exists()
        # Old edge file should NOT exist.
        assert not (run_path / "edges.jsonl").exists()
        # Old split files should NOT exist.
        assert not (run_path / "input_transitions.jsonl").exists()
        assert not (run_path / "output_transitions.jsonl").exists()


def test_list_runs():
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        run1 = _make_populated_run("run_a")
        run2 = _make_populated_run("run_b")
        store.save_run(run1)
        store.save_run(run2)
        listed = store.list_runs()
        ids = [r["run_id"] for r in listed]
        assert "run_a" in ids
        assert "run_b" in ids


def test_incremental_save():
    """Saving twice should append only new records."""
    run = init(_req(), run_id="rt_incr")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)

        # Add more data.
        t1 = run.transition([run.root_node_id], _tp())
        store.save_run(run)

        loaded = store.load_run("rt_incr")
        assert len(loaded.run_graph.transitions) == 1
        assert len(loaded.run_graph.nodes) == 2  # root + output


def test_append_batch_rejects_work_session_user_mismatch():
    run = init(_req(), run_id="rt_ws_conflict")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
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
