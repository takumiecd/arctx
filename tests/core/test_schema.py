"""Tests for Node, Transition, and Payload schema classes."""

from __future__ import annotations

import pytest

from stag.core.schema.graph import Node, Transition
from stag.core.schema.payloads import (
    CutPayload,
    DiffSummary,
    GitChangePayload,
    NodePayload,
    PayloadBase,
    TransitionPayload,
    payload_from_dict,
    register_payload_class,
)


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
# Transition
# ---------------------------------------------------------------------------


def test_transition_single_output():
    t = Transition(
        transition_id="t_1",
        input_node_ids=("n_a",),
        output_node_id="n_b",
    )
    assert t.output_node_id == "n_b"
    assert t.input_node_ids == ("n_a",)


def test_transition_to_dict():
    t = Transition(transition_id="t_1", input_node_ids=("n_a",), output_node_id="n_b")
    d = t.to_dict()
    assert d["transition_id"] == "t_1"
    assert d["output_node_id"] == "n_b"


def test_transition_multi_input():
    t = Transition(
        transition_id="t_join",
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
# TransitionPayload
# ---------------------------------------------------------------------------


def test_transition_payload_construction():
    p = TransitionPayload(
        payload_id="pl_2",
        target_id="t_1",
        type="experiment",
        content={"lr": 0.01},
    )
    assert p.target_kind == "transition"
    assert p.payload_type == "transition_payload"


# ---------------------------------------------------------------------------
# CutPayload
# ---------------------------------------------------------------------------


def test_cut_payload_node():
    c = CutPayload(payload_id="pl_c", target_id="n_x", target_kind="node", reason="stale")
    assert c.target_kind == "node"
    assert c.payload_type == "cut"
    assert c.reason == "stale"


def test_cut_payload_transition():
    c = CutPayload(payload_id="pl_c", target_id="t_x", target_kind="transition")
    assert c.target_kind == "transition"


# ---------------------------------------------------------------------------
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
    assert g.target_kind == "transition"
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


def test_payload_from_dict_transition_payload():
    data = {"payload_type": "transition_payload", "payload_id": "pl_2", "target_id": "t_1",
            "target_kind": "transition", "type": "experiment", "content": {}, "metadata": {}}
    p = payload_from_dict(data)
    assert isinstance(p, TransitionPayload)


def test_payload_from_dict_cut():
    data = {"payload_type": "cut", "payload_id": "pl_c", "target_id": "n_x",
            "target_kind": "node", "reason": "old", "metadata": {}}
    p = payload_from_dict(data)
    assert isinstance(p, CutPayload)
    assert p.reason == "old"


def test_payload_from_dict_unknown_type_fallback_to_generic():
    data = {"payload_type": "my_custom_type", "payload_id": "pl_u",
            "target_id": "t_x", "target_kind": "transition", "foo": "bar"}
    p = payload_from_dict(data)
    assert isinstance(p, TransitionPayload)
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
        target_kind: Literal["transition"] = field(default="transition", init=False)
        payload_type: str = field(default="my_payload_test", init=False)

        def to_dict(self):
            return {"payload_id": self.payload_id, "target_id": self.target_id,
                    "target_kind": self.target_kind, "payload_type": self.payload_type,
                    "score": self.score}

    register_payload_class(MyPayload)
    data = {"payload_type": "my_payload_test", "payload_id": "pl_m",
            "target_id": "t_1", "target_kind": "transition", "score": 0.9}
    p = payload_from_dict(data)
    assert isinstance(p, MyPayload)
    assert p.score == 0.9
