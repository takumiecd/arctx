"""Tests for Node, Step, and Payload schema classes."""

from __future__ import annotations

import pytest

from arctx.core.schema.graph import Node, Step
from arctx.core.schema.payloads import (
    CutPayload,
    JoinPayload,
    NodePayload,
    PayloadBase,
    StepPayload,
    payload_from_dict,
    register_payload_class,
)
from arctx.ext.git.payloads import DiffSummary, GitChangePayload

# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


def test_node_construction():
    n = Node(node_id="n_abc")
    assert n.node_id == "n_abc"
    assert n.metadata == {}


def test_node_to_dict_roundtrip():
    n = Node(node_id="n_x", metadata={"k": "v"})
    d = n.to_dict()
    assert d["node_id"] == "n_x"
    assert d["metadata"] == {"k": "v"}


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


def test_step_single_output():
    t = Step(
        step_id="t_1",
        input_node_ids=("n_a",),
        output_node_id="n_b",
    )
    assert t.output_node_id == "n_b"
    assert t.input_node_ids == ("n_a",)


def test_step_to_dict():
    t = Step(step_id="t_1", input_node_ids=("n_a",), output_node_id="n_b")
    d = t.to_dict()
    assert d["step_id"] == "t_1"
    assert d["output_node_id"] == "n_b"


def test_step_multi_input():
    t = Step(
        step_id="t_join",
        input_node_ids=("n_a", "n_b"),
        output_node_id="n_c",
    )
    assert len(t.input_node_ids) == 2


# ---------------------------------------------------------------------------
# PayloadBase ABC
# ---------------------------------------------------------------------------


def test_payload_base_is_abstract():
    with pytest.raises(TypeError):
        PayloadBase()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# NodePayload
# ---------------------------------------------------------------------------


def test_node_payload_construction():
    p = NodePayload(
        payload_id="pl_1",
        target_id="n_a",
        type="note",
        content={"text": "hello"},
    )
    assert p.target_kind == "node"
    assert p.payload_type == "node_payload"
    assert p.type == "note"
    assert p.content["text"] == "hello"


def test_node_payload_to_dict():
    p = NodePayload(payload_id="pl_1", target_id="n_a", type="note")
    d = p.to_dict()
    assert d["payload_type"] == "node_payload"
    assert d["target_kind"] == "node"


# ---------------------------------------------------------------------------
# StepPayload
# ---------------------------------------------------------------------------


def test_step_payload_construction():
    p = StepPayload(
        payload_id="pl_2",
        target_id="t_1",
        type="experiment",
        content={"lr": 0.01},
    )
    assert p.target_kind == "step"
    assert p.payload_type == "step_payload"


# ---------------------------------------------------------------------------
# CutPayload
# ---------------------------------------------------------------------------


def test_cut_payload_node():
    c = CutPayload(payload_id="pl_c", target_id="n_x", target_kind="node", reason="stale")
    assert c.target_kind == "node"
    assert c.payload_type == "cut"
    assert c.reason == "stale"


def test_cut_payload_step():
    c = CutPayload(payload_id="pl_c", target_id="t_x", target_kind="step")
    assert c.target_kind == "step"


# GitChangePayload
# ---------------------------------------------------------------------------


def test_git_change_payload():
    diff = DiffSummary(files_changed=2, insertions=10, deletions=3)
    g = GitChangePayload(
        payload_id="pl_g",
        target_id="t_1",
        branch="main",
        head_commit="abc123",
        diff_summary=diff,
    )
    assert g.target_kind == "step"
    assert g.payload_type == "git_change"
    d = g.to_dict()
    assert d["branch"] == "main"
    assert d["diff_summary"]["insertions"] == 10


# ---------------------------------------------------------------------------
# payload_from_dict
# ---------------------------------------------------------------------------


def test_payload_from_dict_node_payload():
    data = {"payload_type": "node_payload", "payload_id": "pl_1", "target_id": "n_a",
            "target_kind": "node", "type": "note", "content": {"text": "hi"}, "metadata": {}}
    p = payload_from_dict(data)
    assert isinstance(p, NodePayload)
    assert p.type == "note"


def test_payload_from_dict_step_payload():
    data = {"payload_type": "step_payload", "payload_id": "pl_2", "target_id": "t_1",
            "target_kind": "step", "type": "experiment", "content": {}, "metadata": {}}
    p = payload_from_dict(data)
    assert isinstance(p, StepPayload)


def test_payload_from_dict_cut():
    data = {"payload_type": "cut", "payload_id": "pl_c", "target_id": "n_x",
            "target_kind": "node", "reason": "old", "metadata": {}}
    p = payload_from_dict(data)
    assert isinstance(p, CutPayload)
    assert p.reason == "old"


def test_payload_from_dict_join_payload():
    data = {
        "payload_type": "join",
        "payload_id": "pl_j",
        "target_id": "t_x",
        "target_kind": "step",
        "joined_views": ["main", "experiment"],
        "metadata": {},
    }
    p = payload_from_dict(data)
    assert isinstance(p, JoinPayload)
    assert p.joined_views == ("main", "experiment")


def test_payload_from_dict_unknown_type_fallback_to_generic():
    data = {"payload_type": "my_custom_type", "payload_id": "pl_u",
            "target_id": "t_x", "target_kind": "step", "foo": "bar"}
    p = payload_from_dict(data)
    assert isinstance(p, StepPayload)
    assert p.type == "my_custom_type"


def test_payload_from_dict_unknown_node_type_fallback():
    data = {"payload_type": "mystery", "payload_id": "pl_m",
            "target_id": "n_x", "target_kind": "node"}
    p = payload_from_dict(data)
    assert isinstance(p, NodePayload)
    assert p.type == "mystery"


# ---------------------------------------------------------------------------
# register_payload_class
# ---------------------------------------------------------------------------


def test_register_custom_payload_class():
    from dataclasses import dataclass, field
    from typing import Literal

    @dataclass(frozen=True)
    class MyPayload(PayloadBase):
        payload_id: str
        target_id: str
        score: float = 0.0
        target_kind: Literal["step"] = field(default="step", init=False)
        payload_type: str = field(default="my_payload_test", init=False)

        def to_dict(self):
            return {"payload_id": self.payload_id, "target_id": self.target_id,
                    "target_kind": self.target_kind, "payload_type": self.payload_type,
                    "score": self.score}

    register_payload_class(MyPayload)
    data = {"payload_type": "my_payload_test", "payload_id": "pl_m",
            "target_id": "t_1", "target_kind": "step", "score": 0.9}
    p = payload_from_dict(data)
    assert isinstance(p, MyPayload)
    assert p.score == 0.9
