"""Tests for the RunHandle public verbs."""

from __future__ import annotations

import pytest

from optagent import init
from optagent.core.cuts import is_active_node, is_inactive_output_transition
from optagent.core.schema.payloads import (
    CutPayload,
    NotePayload,
    PlanPayload,
    PredictionPayload,
    ResultPayload,
)
from optagent.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _plan_payload(intent: str = "test") -> PlanPayload:
    return PlanPayload(payload_id="pending", target_id="pending", intent=intent)


def test_init_seeds_root_node_and_main_view():
    run = init(_req(), run_id="t_init")
    assert run.root_node_id == "n_0000"
    assert "n_0000" in run.run_graph.nodes
    assert "main" in run.views
    assert "n_0000" in run.views["main"].node_ids


def test_plan_creates_input_transition():
    run = init(_req(), run_id="t_plan")
    it = run.plan([run.root_node_id], _plan_payload("x"))
    assert it.input_transition_id in run.run_graph.input_transitions
    assert run.root_node_id in it.input_node_ids
    # PlanPayload attached
    payloads = run.run_graph.payloads_for_input_transition(it.input_transition_id)
    plan_payload = next(p for p in payloads if isinstance(p, PlanPayload))
    assert plan_payload.payload_id in run.views["main"].payload_ids


def test_plan_multi_input_nodes():
    run = init(_req(), run_id="t_plan_multi")
    # add a second node via observe
    it1 = run.plan([run.root_node_id], _plan_payload())
    ot1 = run.observe(it1.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    second_node = ot1.to_node_id
    it2 = run.plan([run.root_node_id, second_node], _plan_payload("merge"))
    assert tuple(it2.input_node_ids) == (run.root_node_id, second_node)


def test_observe_creates_output_transition_with_result_payload():
    run = init(_req(), run_id="t_obs")
    it = run.plan([run.root_node_id], _plan_payload())
    result = ResultPayload(payload_id="x", target_id="x", status="completed", metrics={"a": 1.0})
    ot = run.observe(it.input_transition_id, result)
    assert ot.output_transition_id in run.run_graph.output_transitions
    payloads = run.run_graph.payloads_for_output_transition(ot.output_transition_id)
    assert any(isinstance(p, ResultPayload) for p in payloads)


def test_observe_creates_new_output_node():
    run = init(_req(), run_id="t_obs_node")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    assert ot.to_node_id in run.run_graph.nodes
    assert ot.to_node_id != run.root_node_id


def test_predict_creates_prediction_output_transitions():
    run = init(_req(), run_id="t_pred")
    it = run.plan([run.root_node_id], _plan_payload())
    ots = run.predict(it.input_transition_id, max_outcomes=3)
    assert len(ots) == 3
    for ot in ots:
        payloads = run.run_graph.payloads_for_output_transition(ot.output_transition_id)
        assert any(isinstance(p, PredictionPayload) for p in payloads)


def test_note_attaches_to_node():
    run = init(_req(), run_id="t_note")
    note = run.note(run.root_node_id, "baseline setup", tags=["context"])
    assert isinstance(note, NotePayload)
    assert note.target_id == run.root_node_id
    payloads = run.run_graph.payloads_for_node(run.root_node_id)
    assert any(isinstance(p, NotePayload) for p in payloads)
    assert note.payload_id in run.views["main"].payload_ids


def test_rewind_input_transition_cuts_it_and_its_ots():
    run = init(_req(), run_id="t_rew_it")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    cut = run.rewind(it.input_transition_id, target_kind="input_transition", reason="undo")
    assert isinstance(cut, CutPayload)
    assert cut.target_kind == "input_transition"
    assert is_inactive_output_transition(run.run_graph, ot.output_transition_id)
    assert not is_active_node(run.run_graph, ot.to_node_id)


def test_rewind_output_transition_cuts_only_that_ot():
    run = init(_req(), run_id="t_rew_ot")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.rewind(ot.output_transition_id, target_kind="output_transition")
    assert is_inactive_output_transition(run.run_graph, ot.output_transition_id)
    assert not is_active_node(run.run_graph, ot.to_node_id)


def test_plan_on_cut_node_raises():
    run = init(_req(), run_id="t_plan_cut")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.rewind(ot.output_transition_id, target_kind="output_transition")
    with pytest.raises(ValueError):
        run.plan([ot.to_node_id], _plan_payload())


def test_rewind_already_cut_raises():
    run = init(_req(), run_id="t_rew_dup")
    it = run.plan([run.root_node_id], _plan_payload())
    run.rewind(it.input_transition_id, target_kind="input_transition")
    with pytest.raises(ValueError):
        run.rewind(it.input_transition_id, target_kind="input_transition")


def test_trace_walks_backwards():
    run = init(_req(), run_id="t_trace")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    ctx = run.trace(ot.to_node_id)
    assert ctx.current_node_id == ot.to_node_id
    assert run.root_node_id in ctx.past_node_ids
    assert ot.output_transition_id in ctx.output_transition_ids
    assert it.input_transition_id in ctx.input_transition_ids


def test_trace_includes_predictions_when_requested():
    run = init(_req(), run_id="t_trace_pred")
    it = run.plan([run.root_node_id], _plan_payload())
    pred_ots = run.predict(it.input_transition_id, max_outcomes=2)
    obs_ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    ctx = run.trace(obs_ot.to_node_id, include_predictions=True)
    for pot in pred_ots:
        assert pot.output_transition_id in ctx.prediction_output_transition_ids


def test_view_create_and_list():
    run = init(_req(), run_id="t_view")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    view = run.view_create("exp-a", root_node_ids=[ot.to_node_id])
    assert "exp-a" in run.views
    views = run.view_list()
    names = [v.name for v in views]
    assert "main" in names
    assert "exp-a" in names


def test_view_show():
    run = init(_req(), run_id="t_view_show")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.view_create("branch", root_node_ids=[ot.to_node_id])
    v = run.view_show("branch")
    assert v.name == "branch"


def test_view_merge_into_main():
    run = init(_req(), run_id="t_view_merge")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.view_create("branch", root_node_ids=[run.root_node_id])
    # add some records in branch view
    it2 = run.plan([run.root_node_id], _plan_payload("branch work"), view="branch")
    ot2 = run.observe(it2.input_transition_id, ResultPayload(payload_id="y", target_id="y", status="completed"), view="branch")
    merged = run.view_merge("branch", into="main")
    assert it2.input_transition_id in merged.input_transition_ids
    branch_plan_payloads = run.run_graph.payloads_for_input_transition(it2.input_transition_id)
    assert branch_plan_payloads[0].payload_id in merged.payload_ids
    assert ot2.output_transition_id in merged.output_transition_ids
