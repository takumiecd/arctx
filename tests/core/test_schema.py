"""Tests for the schema dataclasses and payload round-trip."""

from __future__ import annotations

from optagent.core.schema.graph import InputTransition, Node, OutputTransition
from optagent.core.schema.payloads import (
    CutPayload,
    NotePayload,
    PayloadBase,
    PlanPayload,
    PredictionPayload,
    ResultPayload,
    payload_from_dict,
)
from optagent.core.schema.requirements import Requirement


def test_node_minimal():
    n = Node(node_id="n_0001")
    assert n.to_dict()["node_id"] == "n_0001"


def test_input_transition_fields():
    it = InputTransition(
        input_transition_id="it_0001",
        input_node_ids=("n_a", "n_b"),
    )
    d = it.to_dict()
    assert d["input_transition_id"] == "it_0001"
    assert d["input_node_ids"] == ["n_a", "n_b"]


def test_output_transition_fields():
    ot = OutputTransition(
        output_transition_id="ot_0001",
        input_transition_id="it_0001",
        to_node_id="n_c",
    )
    d = ot.to_dict()
    assert d["output_transition_id"] == "ot_0001"
    assert d["to_node_id"] == "n_c"


def test_note_payload_target_kind():
    np = NotePayload(payload_id="pl_1", target_id="n_a", text="hello")
    assert isinstance(np, PayloadBase)
    assert np.target_kind == "node"
    assert np.payload_type == "note"
    assert np.to_dict()["payload_type"] == "note"


def test_plan_payload_target_kind():
    pp = PlanPayload(payload_id="pl_2", target_id="it_0001", intent="do something")
    assert pp.target_kind == "input_transition"
    assert pp.payload_type == "plan_payload"


def test_prediction_payload_target_kind():
    pred = PredictionPayload(payload_id="pl_3", target_id="ot_0001", confidence=0.8)
    assert pred.target_kind == "output_transition"
    assert pred.payload_type == "prediction"


def test_result_payload_round_trip():
    rp = ResultPayload(
        payload_id="pl_4",
        target_id="ot_0001",
        status="completed",
        artifacts=("a/b",),
        metrics={"score": 0.5},
        matched_prediction_output_id="ot_pred_1",
    )
    rebuilt = payload_from_dict(rp.to_dict())
    assert isinstance(rebuilt, ResultPayload)
    assert rebuilt.status == "completed"
    assert rebuilt.metrics["score"] == 0.5
    assert rebuilt.matched_prediction_output_id == "ot_pred_1"


def test_cut_payload_input_transition_round_trip():
    cp = CutPayload(
        payload_id="pl_5",
        target_id="it_0001",
        target_kind="input_transition",
        cut_at="2026-05-08T00:00:00Z",
        reason="test",
    )
    rebuilt = payload_from_dict(cp.to_dict())
    assert isinstance(rebuilt, CutPayload)
    assert rebuilt.target_kind == "input_transition"
    assert rebuilt.reason == "test"


def test_cut_payload_output_transition_round_trip():
    cp = CutPayload(
        payload_id="pl_6",
        target_id="ot_0001",
        target_kind="output_transition",
        cut_at="2026-05-08T00:00:00Z",
    )
    rebuilt = payload_from_dict(cp.to_dict())
    assert isinstance(rebuilt, CutPayload)
    assert rebuilt.target_kind == "output_transition"


def test_note_payload_round_trip():
    np = NotePayload(
        payload_id="pl_7",
        target_id="n_a",
        text="baseline",
        tags=("context", "setup"),
    )
    rebuilt = payload_from_dict(np.to_dict())
    assert isinstance(rebuilt, NotePayload)
    assert rebuilt.text == "baseline"
    assert rebuilt.tags == ("context", "setup")


def test_plan_payload_round_trip():
    pp = PlanPayload(
        payload_id="pl_8",
        target_id="it_0001",
        intent="do something",
        action_type="analysis",
        assumptions=("a1", "a2"),
    )
    rebuilt = payload_from_dict(pp.to_dict())
    assert isinstance(rebuilt, PlanPayload)
    assert rebuilt.intent == "do something"
    assert rebuilt.assumptions == ("a1", "a2")


def test_prediction_payload_round_trip():
    pred = PredictionPayload(
        payload_id="pl_9",
        target_id="ot_0001",
        predicted_metrics={"accuracy": 0.9},
        confidence=0.7,
        predictor="gpt4",
    )
    rebuilt = payload_from_dict(pred.to_dict())
    assert isinstance(rebuilt, PredictionPayload)
    assert rebuilt.predicted_metrics["accuracy"] == 0.9
    assert rebuilt.predictor == "gpt4"
