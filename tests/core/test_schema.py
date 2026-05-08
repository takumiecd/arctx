"""Tests for the schema dataclasses and payload round-trip."""

from __future__ import annotations

from optagent.core.schema.graph import Node, Transition
from optagent.core.schema.payloads import (
    CutPayload,
    DerivedPayload,
    MatchPayload,
    ResultPayload,
    PayloadBase,
    SnapshotPayload,
    payload_from_dict,
)
from optagent.core.schema.plans import Plan
from optagent.core.schema.requirements import Requirement
from optagent.core.schema.snapshots import StateSnapshot


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="t", target_id="x")


def test_node_minimal():
    n = Node(node_id="n_0001")
    assert n.to_dict()["node_id"] == "n_0001"


def test_transition_fields():
    t = Transition(
        transition_id="t_0001",
        parent_plan_id="plan_0001",
        from_node_id="n_a",
        to_node_id="n_b",
    )
    d = t.to_dict()
    assert d["from_node_id"] == "n_a"
    assert d["to_node_id"] == "n_b"


def test_plan_no_kind():
    p = Plan(
        plan_id="plan_0001",
        grounded_node_id="n_a",
        action_type="analysis",
        intent="test",
    )
    d = p.to_dict()
    assert "plan_kind" not in d
    assert d["grounded_node_id"] == "n_a"


def test_snapshot_payload_target_kind():
    snap = StateSnapshot(requirement=_req())
    sp = SnapshotPayload(payload_id="pl_1", target_id="n_a", snapshot=snap)
    assert isinstance(sp, PayloadBase)
    assert sp.target_kind == "node"
    assert sp.payload_type == "snapshot"
    d = sp.to_dict()
    assert d["payload_type"] == "snapshot"


def test_result_payload_round_trip():
    rp = ResultPayload(
        payload_id="pl_2",
        target_id="t_a",
        status="completed",
        artifacts=("a/b",),
        metrics={"score": 0.5},
    )
    rebuilt = payload_from_dict(rp.to_dict())
    assert isinstance(rebuilt, ResultPayload)
    assert rebuilt.status == "completed"
    assert rebuilt.metrics["score"] == 0.5


def test_derived_payload_round_trip():
    dp = DerivedPayload(
        payload_id="pl_3",
        target_id="t_a",
        derived_type="finding",
        payload={"text": "hello"},
        generator="cli",
    )
    rebuilt = payload_from_dict(dp.to_dict())
    assert isinstance(rebuilt, DerivedPayload)
    assert rebuilt.payload["text"] == "hello"


def test_match_payload_round_trip():
    mp = MatchPayload(
        payload_id="pl_4",
        target_id="t_a",
        matched_transition_id="t_pred_1",
        match_status="compatible",
    )
    rebuilt = payload_from_dict(mp.to_dict())
    assert isinstance(rebuilt, MatchPayload)
    assert rebuilt.matched_transition_id == "t_pred_1"


def test_cut_payload_round_trip():
    cp = CutPayload(
        payload_id="pl_5",
        target_id="t_a",
        cut_at="2026-05-08T00:00:00Z",
        rewound_to_node_id="n_a",
        reason="test",
    )
    rebuilt = payload_from_dict(cp.to_dict())
    assert isinstance(rebuilt, CutPayload)
    assert rebuilt.reason == "test"


def test_snapshot_payload_round_trip():
    snap = StateSnapshot(requirement=_req())
    sp = SnapshotPayload(payload_id="pl_6", target_id="n_a", snapshot=snap)
    rebuilt = payload_from_dict(sp.to_dict())
    assert isinstance(rebuilt, SnapshotPayload)
    assert rebuilt.snapshot.requirement.requirement_id == "r"
