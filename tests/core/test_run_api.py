"""Tests for the RunHandle public verbs."""

from __future__ import annotations

import pytest

from stag import init
from stag.core.cuts import is_active_node, is_inactive_output_transition
from stag.core.schema.payloads import (
    CutPayload,
    NotePayload,
    PlanPayload,
    PredictionPayload,
    ResultPayload,
)
from stag.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _plan_payload(intent: str = "test") -> PlanPayload:
    return PlanPayload(payload_id="pending", target_id="pending", intent=intent)


def test_init_seeds_root_node_and_main_view():
    run = init(_req(), run_id="t_init")
    assert run.root_node_id == "n_0000"
    assert "n_0000" in run.run_graph.nodes
    assert "main" in run.run_graph.views
    assert run.run_graph.views["main"].root_node_id == "n_0000"


def test_plan_creates_input_transition():
    run = init(_req(), run_id="t_plan")
    it = run.plan([run.root_node_id], _plan_payload("x"))
    assert it.input_transition_id in run.run_graph.input_transitions
    assert run.root_node_id in it.input_node_ids
    # PlanPayload attached
    payloads = run.run_graph.payloads_for_input_transition(it.input_transition_id)
    assert any(isinstance(p, PlanPayload) for p in payloads)


def test_anchor_creates_scope_refinement_branch_point():
    run = init(_req(), run_id="t_anchor")
    ot = run.anchor(run.root_node_id, "common benchmark setup")
    it = run.run_graph.input_transitions[ot.input_transition_id]

    assert tuple(it.input_node_ids) == (run.root_node_id,)
    assert ot.to_node_id in run.run_graph.nodes

    plan_payloads = run.run_graph.payloads_for_input_transition(it.input_transition_id)
    plan = next(p for p in plan_payloads if isinstance(p, PlanPayload))
    assert plan.intent == "common benchmark setup"
    assert plan.action_type == "scope_refinement"
    assert plan.metadata["kind"] == "anchor"

    result_payloads = run.run_graph.payloads_for_output_transition(ot.output_transition_id)
    result = next(p for p in result_payloads if isinstance(p, ResultPayload))
    assert result.status == "completed"
    assert result.metadata["kind"] == "anchor"
    assert result.metadata["label"] == "common benchmark setup"


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


def test_cut_input_transition_cuts_it_and_its_ots():
    run = init(_req(), run_id="t_rew_it")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    cut = run.cut(it.input_transition_id, target_kind="input_transition", reason="undo")
    assert isinstance(cut, CutPayload)
    assert cut.target_kind == "input_transition"
    assert is_inactive_output_transition(run.run_graph, ot.output_transition_id)
    assert not is_active_node(run.run_graph, ot.to_node_id)


def test_cut_output_transition_cuts_only_that_ot():
    run = init(_req(), run_id="t_rew_ot")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.cut(ot.output_transition_id, target_kind="output_transition")
    assert is_inactive_output_transition(run.run_graph, ot.output_transition_id)
    assert not is_active_node(run.run_graph, ot.to_node_id)


def test_plan_on_cut_node_raises():
    run = init(_req(), run_id="t_plan_cut")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.cut(ot.output_transition_id, target_kind="output_transition")
    with pytest.raises(ValueError):
        run.plan([ot.to_node_id], _plan_payload())


def test_cut_already_cut_raises():
    run = init(_req(), run_id="t_rew_dup")
    it = run.plan([run.root_node_id], _plan_payload())
    run.cut(it.input_transition_id, target_kind="input_transition")
    with pytest.raises(ValueError):
        run.cut(it.input_transition_id, target_kind="input_transition")


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
    view = run.view_create("exp-a", root_node_id=ot.to_node_id)
    assert "exp-a" in run.run_graph.views
    views = run.view_list()
    names = [v.name for v in views]
    assert "main" in names
    assert "exp-a" in names


def test_view_show():
    run = init(_req(), run_id="t_view_show")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.view_create("branch", root_node_id=ot.to_node_id)
    v = run.view_show("branch")
    assert v.name == "branch"


def test_view_reachable_from():
    run = init(_req(), run_id="t_view_reach")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    # create a second branch from the observed node
    it2 = run.plan([ot.to_node_id], _plan_payload("branch"))
    ot2 = run.observe(it2.input_transition_id, ResultPayload(payload_id="y", target_id="y", status="completed"))

    reachable = run.run_graph.reachable_from(run.root_node_id)
    assert run.root_node_id in reachable["node_ids"]
    assert ot.to_node_id in reachable["node_ids"]
    assert ot2.to_node_id in reachable["node_ids"]
    assert it.input_transition_id in reachable["input_transition_ids"]
    assert it2.input_transition_id in reachable["input_transition_ids"]
    assert ot.output_transition_id in reachable["output_transition_ids"]
    assert ot2.output_transition_id in reachable["output_transition_ids"]


def test_multiple_observed_outputs_per_input_transition():
    run = init(_req(), run_id="t_multi_obs")
    it = run.plan([run.root_node_id], _plan_payload())
    ot1 = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    ot2 = run.observe(it.input_transition_id, ResultPayload(payload_id="y", target_id="y", status="failed"))
    assert ot1.output_transition_id != ot2.output_transition_id
    assert ot1.to_node_id != ot2.to_node_id
    ots = run.run_graph.output_transitions_from_it[it.input_transition_id]
    assert ot1.output_transition_id in ots
    assert ot2.output_transition_id in ots


def test_predict_on_cut_input_transition_raises():
    run = init(_req(), run_id="t_pred_cut")
    it = run.plan([run.root_node_id], _plan_payload())
    run.cut(it.input_transition_id, target_kind="input_transition")
    with pytest.raises(ValueError, match="inactive"):
        run.predict(it.input_transition_id)


def test_observe_on_cut_input_transition_raises():
    run = init(_req(), run_id="t_obs_cut")
    it = run.plan([run.root_node_id], _plan_payload())
    run.cut(it.input_transition_id, target_kind="input_transition")
    with pytest.raises(ValueError, match="inactive"):
        run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))


def test_observe_on_input_transition_with_cut_input_node_raises():
    run = init(_req(), run_id="t_obs_cut_node")
    it1 = run.plan([run.root_node_id], _plan_payload())
    ot1 = run.observe(it1.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    # cut the OT so ot1.to_node_id becomes inactive
    run.cut(ot1.output_transition_id, target_kind="output_transition")
    # plan rooted at the now-inactive node
    it2 = run.run_graph.input_transitions.get(
        next(
            (it_id for it_id, it in run.run_graph.input_transitions.items()
             if ot1.to_node_id in it.input_node_ids),
            None,
        )
    )
    # instead, manually wire: create IT with inactive input node and check observe rejects it
    from stag.core.schema.graph import InputTransition
    it_bad = InputTransition(input_transition_id="it_bad", input_node_ids=(ot1.to_node_id,))
    run.run_graph.add_input_transition(it_bad)
    with pytest.raises(ValueError, match="inactive"):
        run.observe("it_bad", ResultPayload(payload_id="z", target_id="z", status="completed"))


def test_outcomes_returns_predictions_observations_split():
    run = init(_req(), run_id="t_outcomes_split")
    it = run.plan([run.root_node_id], _plan_payload())
    pred_ots = run.predict(it.input_transition_id, max_outcomes=2)
    obs_ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    out = run.outcomes(it.input_transition_id)
    assert out["input_transition_id"] == it.input_transition_id
    assert obs_ot.output_transition_id in out["observations"]
    assert obs_ot.output_transition_id in out["active_observations"]
    assert out["inactive_observations"] == []
    for pot in pred_ots:
        assert pot.output_transition_id in out["predictions"]


def test_outcomes_marks_inactive_observation():
    run = init(_req(), run_id="t_outcomes_inactive")
    it = run.plan([run.root_node_id], _plan_payload())
    ot1 = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    ot2 = run.observe(it.input_transition_id, ResultPayload(payload_id="y", target_id="y", status="completed"))
    run.cut(ot1.output_transition_id, target_kind="output_transition")
    out = run.outcomes(it.input_transition_id)
    assert ot1.output_transition_id in out["observations"]
    assert ot1.output_transition_id in out["inactive_observations"]
    assert ot1.output_transition_id not in out["active_observations"]
    assert ot2.output_transition_id in out["active_observations"]


# ---------------------------------------------------------------------------
# trace DAG tests
# ---------------------------------------------------------------------------

def test_trace_collects_all_input_nodes_of_multi_input_it():
    """multi-input IT の全 input_node_ids が past_node_ids に含まれること。"""
    run = init(_req(), run_id="t_trace_multi_input")
    # Create two separate nodes by making two observations from root
    it_a = run.plan([run.root_node_id], _plan_payload("branch_a"))
    ot_a = run.observe(it_a.input_transition_id, ResultPayload(payload_id="ra", target_id="ra", status="completed"))
    it_b = run.plan([run.root_node_id], _plan_payload("branch_b"))
    ot_b = run.observe(it_b.input_transition_id, ResultPayload(payload_id="rb", target_id="rb", status="completed"))

    # Merge: IT with both nodes as inputs
    it_merge = run.plan([ot_a.to_node_id, ot_b.to_node_id], _plan_payload("merge"))
    ot_merge = run.observe(it_merge.input_transition_id, ResultPayload(payload_id="rm", target_id="rm", status="completed"))

    ctx = run.trace(ot_merge.to_node_id)
    assert ot_a.to_node_id in ctx.past_node_ids
    assert ot_b.to_node_id in ctx.past_node_ids
    assert run.root_node_id in ctx.past_node_ids


def test_trace_skips_inactive_observed_ots():
    """observe → cut した OT は trace に出てこないこと。"""
    run = init(_req(), run_id="t_trace_inactive")
    it = run.plan([run.root_node_id], _plan_payload())
    ot = run.observe(it.input_transition_id, ResultPayload(payload_id="x", target_id="x", status="completed"))
    run.cut(ot.output_transition_id, target_kind="output_transition")

    ctx = run.trace(ot.to_node_id)
    assert ot.output_transition_id not in ctx.output_transition_ids
    assert it.input_transition_id not in ctx.input_transition_ids
    assert run.root_node_id not in ctx.past_node_ids


def test_trace_dedupes_revisited_nodes():
    """同じノードが複数経路から到達されても past_node_ids に重複しない。"""
    run = init(_req(), run_id="t_trace_dedup")
    # Two branches from root that both converge to the same merge node
    it_a = run.plan([run.root_node_id], _plan_payload("a"))
    ot_a = run.observe(it_a.input_transition_id, ResultPayload(payload_id="ra", target_id="ra", status="completed"))
    it_b = run.plan([run.root_node_id], _plan_payload("b"))
    ot_b = run.observe(it_b.input_transition_id, ResultPayload(payload_id="rb", target_id="rb", status="completed"))

    it_merge = run.plan([ot_a.to_node_id, ot_b.to_node_id], _plan_payload("merge"))
    ot_merge = run.observe(it_merge.input_transition_id, ResultPayload(payload_id="rm", target_id="rm", status="completed"))

    ctx = run.trace(ot_merge.to_node_id)
    # root_node_id appears via both branches but must appear only once
    assert ctx.past_node_ids.count(run.root_node_id) == 1


# ---------------------------------------------------------------------------
# observe matched_prediction_output_id validation tests
# ---------------------------------------------------------------------------

def test_observe_matched_prediction_unknown_id_raises():
    run = init(_req(), run_id="t_mpid_unknown")
    it = run.plan([run.root_node_id], _plan_payload())
    result = ResultPayload(
        payload_id="x", target_id="x", status="completed",
        matched_prediction_output_id="nonexistent_ot",
    )
    with pytest.raises(KeyError, match="nonexistent_ot"):
        run.observe(it.input_transition_id, result)


def test_observe_matched_prediction_not_a_prediction_raises():
    """ResultPayload のみ持つ OT を matched に指定 → ValueError。"""
    run = init(_req(), run_id="t_mpid_not_pred")
    it = run.plan([run.root_node_id], _plan_payload())
    # Create an observed OT (has ResultPayload, not PredictionPayload)
    obs_ot = run.observe(it.input_transition_id, ResultPayload(payload_id="r1", target_id="r1", status="completed"))

    # Now create another IT and try to observe with matched pointing to the non-prediction OT
    it2 = run.plan([obs_ot.to_node_id], _plan_payload("step2"))
    result = ResultPayload(
        payload_id="r2", target_id="r2", status="completed",
        matched_prediction_output_id=obs_ot.output_transition_id,
    )
    with pytest.raises(ValueError, match="does not point to a prediction"):
        run.observe(it2.input_transition_id, result)


def test_observe_matched_prediction_different_it_raises():
    """別 IT から出た prediction を matched に指定 → ValueError。"""
    run = init(_req(), run_id="t_mpid_diff_it")
    it1 = run.plan([run.root_node_id], _plan_payload("step1"))
    pred_ots = run.predict(it1.input_transition_id, max_outcomes=1)
    pred_ot = pred_ots[0]

    # A second IT from root
    it2 = run.plan([run.root_node_id], _plan_payload("step2"))
    result = ResultPayload(
        payload_id="r2", target_id="r2", status="completed",
        matched_prediction_output_id=pred_ot.output_transition_id,
    )
    with pytest.raises(ValueError, match="belongs to a different input_transition"):
        run.observe(it2.input_transition_id, result)


def test_observe_matched_prediction_inactive_raises():
    """prediction OT を cut した後 matched に指定 → ValueError。"""
    run = init(_req(), run_id="t_mpid_inactive")
    it = run.plan([run.root_node_id], _plan_payload())
    pred_ots = run.predict(it.input_transition_id, max_outcomes=1)
    pred_ot = pred_ots[0]
    run.cut(pred_ot.output_transition_id, target_kind="output_transition")

    result = ResultPayload(
        payload_id="r1", target_id="r1", status="completed",
        matched_prediction_output_id=pred_ot.output_transition_id,
    )
    with pytest.raises(ValueError, match="is inactive"):
        run.observe(it.input_transition_id, result)


def test_observe_matched_prediction_valid_passes():
    """同じ IT 配下、active な prediction を matched に → 成功。"""
    run = init(_req(), run_id="t_mpid_valid")
    it = run.plan([run.root_node_id], _plan_payload())
    pred_ots = run.predict(it.input_transition_id, max_outcomes=2)
    pred_ot = pred_ots[0]

    result = ResultPayload(
        payload_id="r1", target_id="r1", status="completed",
        matched_prediction_output_id=pred_ot.output_transition_id,
    )
    obs_ot = run.observe(it.input_transition_id, result)
    payloads = run.run_graph.payloads_for_output_transition(obs_ot.output_transition_id)
    rp = next(p for p in payloads if isinstance(p, ResultPayload))
    assert rp.matched_prediction_output_id == pred_ot.output_transition_id
