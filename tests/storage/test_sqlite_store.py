"""Tests for SqliteRunStore."""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

from stag import init
from stag.core.schema.payloads import PlanPayload, PredictionPayload, ResultPayload
from stag.core.schema.requirements import Requirement
from stag.storage.base import RunStore
from stag.storage.sqlite import SqliteRunStore


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _plan(intent: str = "x") -> PlanPayload:
    return PlanPayload(payload_id="pending", target_id="pending", intent=intent)


def _result() -> ResultPayload:
    return ResultPayload(payload_id="pending", target_id="pending", status="completed")


# ---------------------------------------------------------------------------
# 1. Round-trip: save_run -> load_run produces semantically equivalent RunHandle
# ---------------------------------------------------------------------------


def test_round_trip_basic():
    run = init(_req(), run_id="sq_basic")
    it = run.plan([run.root_node_id], _plan())
    run.observe(it.input_transition_id, ResultPayload(payload_id="p", target_id="p", status="completed", metrics={"score": 0.9}))

    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_basic")

    assert loaded.run_id == run.run_id
    assert loaded.requirement.requirement_id == run.requirement.requirement_id
    assert len(loaded.run_graph.nodes) == len(run.run_graph.nodes)
    assert len(loaded.run_graph.input_transitions) == len(run.run_graph.input_transitions)
    assert len(loaded.run_graph.output_transitions) == len(run.run_graph.output_transitions)
    assert len(loaded.run_graph.payloads) == len(run.run_graph.payloads)
    assert set(loaded.run_graph.views.keys()) == set(run.run_graph.views.keys())
    assert dict(loaded._counters) == dict(run._counters)


def test_round_trip_with_predictions():
    run = init(_req(), run_id="sq_pred")
    run.note(run.root_node_id, "start", tags=["t"])
    it = run.plan([run.root_node_id], _plan())
    run.predict(it.input_transition_id, max_outcomes=2)
    run.observe(it.input_transition_id, _result())

    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_pred")

    # 1 observed + 2 predicted OTs = 3
    assert len(loaded.run_graph.output_transitions) == 3
    # NotePayload + PlanPayload + 2 PredictionPayloads + 1 ResultPayload = 5
    assert len(loaded.run_graph.payloads) == 5


def test_round_trip_preserves_views():
    run = init(_req(), run_id="sq_views")
    it = run.plan([run.root_node_id], _plan())
    ot = run.observe(it.input_transition_id, _result())
    run.view_create("branch-a", root_node_id=ot.to_node_id)

    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_views")

    assert "main" in loaded.run_graph.views
    assert "branch-a" in loaded.run_graph.views
    assert loaded.run_graph.views["branch-a"].root_node_id == ot.to_node_id


def test_round_trip_secondary_indices():
    """input_transitions_from_node and output_transitions_from_it must be rebuilt."""
    run = init(_req(), run_id="sq_idx")
    it = run.plan([run.root_node_id], _plan())
    ot = run.observe(it.input_transition_id, _result())

    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_idx")

    rg = loaded.run_graph
    assert it.input_transition_id in rg.input_transitions_from_node.get(run.root_node_id, [])
    assert ot.output_transition_id in rg.output_transitions_from_it.get(it.input_transition_id, [])
    assert ot.output_transition_id in rg.output_transitions_to_node.get(ot.to_node_id, [])


def test_round_trip_cut_payload():
    run = init(_req(), run_id="sq_cut")
    it = run.plan([run.root_node_id], _plan())
    ot = run.observe(it.input_transition_id, _result())
    run.cut(ot.output_transition_id, target_kind="output_transition", reason="undo")

    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_cut")

    from stag.core.cuts import is_inactive_output_transition
    assert is_inactive_output_transition(loaded.run_graph, ot.output_transition_id)


def test_prediction_payload_probability_round_trip():
    run = init(_req(), run_id="sq_prob")
    it = run.plan([run.root_node_id], _plan())
    ots = run.predict(
        it.input_transition_id,
        payloads=[
            PredictionPayload(payload_id="pending", target_id="pending", probability=0.8, confidence=0.95)
        ],
    )
    ot_id = ots[0].output_transition_id

    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        store.save_run(run)
        loaded = store.load_run("sq_prob")

    payloads = loaded.run_graph.payloads_for_output_transition(ot_id)
    pred = next(p for p in payloads if isinstance(p, PredictionPayload))
    assert pred.probability == 0.8
    assert pred.confidence == 0.95


# ---------------------------------------------------------------------------
# 2. Delta INSERT: second save only inserts new rows
# ---------------------------------------------------------------------------


def test_second_save_inserts_only_new_nodes():
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        run = init(_req(), run_id="sq_delta")

        store.save_run(run)

        db_path = store.run_path("sq_delta") / "run.db"
        con = sqlite3.connect(str(db_path))
        count_after_first = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        con.close()

        assert count_after_first == 1  # root node only

        it = run.plan([run.root_node_id], _plan())
        run.observe(it.input_transition_id, _result())  # adds 1 new node

        store.save_run(run)

        con = sqlite3.connect(str(db_path))
        count_after_second = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        con.close()

        assert count_after_second == count_after_first + 1


def test_second_save_appends_payloads():
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        run = init(_req(), run_id="sq_delta_pay")

        it = run.plan([run.root_node_id], _plan())
        store.save_run(run)  # PlanPayload in DB

        db_path = store.run_path("sq_delta_pay") / "run.db"
        con = sqlite3.connect(str(db_path))
        count_after_first = con.execute("SELECT COUNT(*) FROM payloads").fetchone()[0]
        con.close()

        run.observe(it.input_transition_id, _result())  # adds ResultPayload
        store.save_run(run)

        con = sqlite3.connect(str(db_path))
        count_after_second = con.execute("SELECT COUNT(*) FROM payloads").fetchone()[0]
        con.close()

        assert count_after_second == count_after_first + 1


# ---------------------------------------------------------------------------
# 3. Disk ahead of memory -> RuntimeError
# ---------------------------------------------------------------------------


def test_disk_ahead_of_memory_raises():
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        run = init(_req(), run_id="sq_corrupt")
        store.save_run(run)

        # Inject a spurious row directly into the DB
        db_path = store.run_path("sq_corrupt") / "run.db"
        con = sqlite3.connect(str(db_path))
        con.execute(
            "INSERT INTO nodes (node_id, data_json) VALUES (?, ?)",
            ("n_fake", '{"node_id": "n_fake", "metadata": {}}'),
        )
        con.commit()
        con.close()

        with pytest.raises(RuntimeError, match="nodes"):
            store.save_run(run)


# ---------------------------------------------------------------------------
# 4. list_runs works
# ---------------------------------------------------------------------------


def test_list_runs():
    with tempfile.TemporaryDirectory() as td:
        store = SqliteRunStore(td)
        run = init(_req(), run_id="sq_list")
        store.save_run(run)

        runs = store.list_runs()
        assert any(r["run_id"] == "sq_list" for r in runs)


def test_list_runs_mixed_with_jsonl(tmp_path):
    """list_runs should work even when the root contains both jsonl and sqlite runs."""
    from stag.storage.jsonl import JsonlRunStore

    sqlite_store = SqliteRunStore(tmp_path)
    jsonl_store = JsonlRunStore(tmp_path)

    run_sq = init(_req(), run_id="mixed_sq")
    run_jl = init(_req(), run_id="mixed_jl")
    sqlite_store.save_run(run_sq)
    jsonl_store.save_run(run_jl)

    runs = sqlite_store.list_runs()
    run_ids = {r["run_id"] for r in runs}
    assert "mixed_sq" in run_ids
    assert "mixed_jl" in run_ids


# ---------------------------------------------------------------------------
# 5. isinstance check against RunStore Protocol
# ---------------------------------------------------------------------------


def test_isinstance_run_store_protocol(tmp_path):
    assert isinstance(SqliteRunStore(tmp_path), RunStore)
