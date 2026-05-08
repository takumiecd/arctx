"""Tests for JsonlRunStore round-trip."""

from __future__ import annotations

import tempfile

from optagent import init
from optagent.core.schema.payloads import (
    NotePayload,
    PlanPayload,
    PredictionPayload,
    ResultPayload,
)
from optagent.core.schema.requirements import Requirement
from optagent.storage.jsonl import JsonlRunStore


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _plan_payload(intent: str = "x") -> PlanPayload:
    return PlanPayload(payload_id="pending", target_id="pending", intent=intent)


def test_round_trip_basic():
    run = init(_req(), run_id="rt_basic")
    it = run.plan([run.root_node_id], _plan_payload())
    result = ResultPayload(payload_id="x", target_id="x", status="completed", metrics={"a": 1.0})
    run.observe(it.input_transition_id, result)

    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        loaded = store.load_run("rt_basic")

    assert loaded.run_id == run.run_id
    assert len(loaded.run_graph.nodes) == len(run.run_graph.nodes)
    assert len(loaded.run_graph.input_transitions) == len(run.run_graph.input_transitions)
    assert len(loaded.run_graph.output_transitions) == len(run.run_graph.output_transitions)
    assert len(loaded.run_graph.payloads) == len(run.run_graph.payloads)


def test_round_trip_with_predictions():
    run = init(_req(), run_id="rt_pred")
    run.note(run.root_node_id, "start note", tags=["setup"])
    it = run.plan([run.root_node_id], _plan_payload())
    run.predict(it.input_transition_id, max_outcomes=3)
    run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))

    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        loaded = store.load_run("rt_pred")

    # 1 observed OT + 3 predicted OTs = 4
    assert len(loaded.run_graph.output_transitions) == 4
    # NotePayload + PlanPayload + 3 PredictionPayloads + 1 ResultPayload = 6
    assert len(loaded.run_graph.payloads) == 6


def test_round_trip_preserves_views():
    run = init(_req(), run_id="rt_views")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.view_create("exp-a", root_node_ids=[ot.to_node_id])

    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        loaded = store.load_run("rt_views")

    assert "main" in loaded.views
    assert "exp-a" in loaded.views
    assert loaded.views["main"].payload_ids == run.views["main"].payload_ids


def test_round_trip_cut_payload():
    run = init(_req(), run_id="rt_cut")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.rewind(ot.output_transition_id, target_kind="output_transition", reason="undo")

    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        loaded = store.load_run("rt_cut")

    from optagent.core.cuts import is_inactive_output_transition
    assert is_inactive_output_transition(loaded.run_graph, ot.output_transition_id)


def test_list_runs_returns_summaries():
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        run = init(_req(), run_id="rt_listing")
        store.save_run(run)
        runs = store.list_runs()
        assert any(r["run_id"] == "rt_listing" for r in runs)
