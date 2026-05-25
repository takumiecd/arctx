"""Tests for RunGraph mutations and lookups."""

from __future__ import annotations

import pytest

from stag.core.run_graph import RunGraph
from stag.core.schema.graph import Node, Transition
from stag.core.schema.payloads import CutPayload, NodePayload, TransitionPayload


def _graph_with_nodes(*node_ids: str) -> RunGraph:
    g = RunGraph()
    for nid in node_ids:
        g.add_node(Node(node_id=nid))
    return g


# ---------------------------------------------------------------------------
# add_node
# ---------------------------------------------------------------------------


def test_add_node_stores_node():
    g = RunGraph()
    g.add_node(Node("n_a"))
    assert "n_a" in g.nodes


def test_add_node_duplicate_raises():
    g = _graph_with_nodes("n_a")
    with pytest.raises(ValueError, match="duplicate node_id"):
        g.add_node(Node("n_a"))


# ---------------------------------------------------------------------------
# add_transition
# ---------------------------------------------------------------------------


def test_add_transition_basic():
    g = _graph_with_nodes("n_a", "n_b")
    t = Transition("t_1", ("n_a",), "n_b")
    g.add_transition(t)
    assert "t_1" in g.transitions
    assert g.transition_by_output_node["n_b"] == "t_1"
    assert "t_1" in g.transitions_by_input_node.get("n_a", [])


def test_add_transition_unknown_input_raises():
    g = _graph_with_nodes("n_a", "n_b")
    with pytest.raises(KeyError, match="unknown input_node_id"):
        g.add_transition(Transition("t_1", ("n_x",), "n_b"))


def test_add_transition_unknown_output_raises():
    g = _graph_with_nodes("n_a")
    with pytest.raises(KeyError, match="unknown output_node_id"):
        g.add_transition(Transition("t_1", ("n_a",), "n_x"))


def test_add_transition_duplicate_output_raises():
    g = _graph_with_nodes("n_a", "n_b", "n_c")
    g.add_transition(Transition("t_1", ("n_a",), "n_b"))
    with pytest.raises(ValueError, match="already used"):
        g.add_transition(Transition("t_2", ("n_a",), "n_b"))


def test_add_transition_duplicate_id_raises():
    g = _graph_with_nodes("n_a", "n_b", "n_c")
    g.add_transition(Transition("t_1", ("n_a",), "n_b"))
    with pytest.raises(ValueError, match="duplicate transition_id"):
        g.add_transition(Transition("t_1", ("n_a",), "n_c"))


# ---------------------------------------------------------------------------
# attach_payload
# ---------------------------------------------------------------------------


def test_attach_node_payload():
    g = _graph_with_nodes("n_a")
    p = NodePayload(payload_id="pl_1", target_id="n_a", type="note")
    g.attach_payload(p)
    assert "pl_1" in g.payloads
    assert "pl_1" in g.payloads_by_node["n_a"]


def test_attach_transition_payload():
    g = _graph_with_nodes("n_a", "n_b")
    g.add_transition(Transition("t_1", ("n_a",), "n_b"))
    p = TransitionPayload(payload_id="pl_2", target_id="t_1", type="experiment")
    g.attach_payload(p)
    assert "pl_2" in g.payloads_by_transition["t_1"]


def test_attach_payload_unknown_node_raises():
    g = RunGraph()
    p = NodePayload(payload_id="pl_1", target_id="n_unknown", type="note")
    with pytest.raises(KeyError):
        g.attach_payload(p)


def test_attach_payload_duplicate_raises():
    g = _graph_with_nodes("n_a")
    p = NodePayload(payload_id="pl_1", target_id="n_a", type="note")
    g.attach_payload(p)
    with pytest.raises(ValueError, match="duplicate payload_id"):
        g.attach_payload(p)


# ---------------------------------------------------------------------------
# Reverse-index lookups
# ---------------------------------------------------------------------------


def test_transitions_from_node():
    g = _graph_with_nodes("n_a", "n_b")
    g.add_transition(Transition("t_1", ("n_a",), "n_b"))
    assert g.transitions_from_node("n_a") == ["t_1"]
    assert g.transitions_from_node("n_b") == []


def test_transition_to_node():
    g = _graph_with_nodes("n_a", "n_b")
    g.add_transition(Transition("t_1", ("n_a",), "n_b"))
    assert g.transition_to_node("n_b") == "t_1"
    assert g.transition_to_node("n_a") is None


def test_transition_inputs():
    g = _graph_with_nodes("n_a", "n_b", "n_c")
    g.add_transition(Transition("t_1", ("n_a", "n_b"), "n_c"))
    assert g.transition_inputs("t_1") == ["n_a", "n_b"]


def test_transition_output():
    g = _graph_with_nodes("n_a", "n_b")
    g.add_transition(Transition("t_1", ("n_a",), "n_b"))
    assert g.transition_output("t_1") == "n_b"


def test_payloads_for_node_filter():
    g = _graph_with_nodes("n_a")
    g.attach_payload(NodePayload("pl_1", "n_a", type="note"))
    g.attach_payload(NodePayload("pl_2", "n_a", type="tag"))
    notes = g.payloads_for_node("n_a", payload_type="node_payload")
    assert len(notes) == 2
    # filter by type string: payload_type is the class discriminator
    all_p = g.payloads_for_node("n_a")
    assert len(all_p) == 2


def test_roots():
    g = _graph_with_nodes("n_a", "n_b")
    g.add_transition(Transition("t_1", ("n_a",), "n_b"))
    assert g.roots() == ["n_a"]
