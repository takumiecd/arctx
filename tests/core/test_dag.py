"""Tests for RunGraph container."""

from __future__ import annotations

import pytest

from optagent.core.run_graph import RunGraph
from optagent.core.schema.graph import InputTransition, Node, OutputTransition
from optagent.core.schema.payloads import NotePayload, ResultPayload


def _base_graph() -> RunGraph:
    g = RunGraph()
    g.add_node(Node(node_id="n_a"))
    g.add_node(Node(node_id="n_b"))
    return g


def test_add_node_duplicate_rejected():
    g = _base_graph()
    with pytest.raises(ValueError):
        g.add_node(Node(node_id="n_a"))


def test_add_input_transition_indexes():
    g = _base_graph()
    it = InputTransition(input_transition_id="it_1", input_node_ids=("n_a",))
    g.add_input_transition(it)
    assert "it_1" in g.input_transitions_from_node["n_a"]


def test_add_input_transition_unknown_node_rejected():
    g = _base_graph()
    with pytest.raises(KeyError):
        g.add_input_transition(
            InputTransition(input_transition_id="it_1", input_node_ids=("n_missing",))
        )


def test_add_output_transition_indexes():
    g = _base_graph()
    it = InputTransition(input_transition_id="it_1", input_node_ids=("n_a",))
    g.add_input_transition(it)
    ot = OutputTransition(output_transition_id="ot_1", input_transition_id="it_1", to_node_id="n_b")
    g.add_output_transition(ot)
    assert "ot_1" in g.output_transitions_from_it["it_1"]
    assert "ot_1" in g.output_transitions_to_node["n_b"]


def test_add_output_transition_unknown_it_rejected():
    g = _base_graph()
    with pytest.raises(KeyError):
        g.add_output_transition(
            OutputTransition(output_transition_id="ot_1", input_transition_id="it_missing", to_node_id="n_b")
        )


def test_attach_payload_to_node():
    g = _base_graph()
    g.attach_payload(NotePayload(payload_id="pl_1", target_id="n_a", text="hi"))
    payloads = g.payloads_for_node("n_a")
    assert len(payloads) == 1
    assert payloads[0].payload_id == "pl_1"


def test_attach_payload_unknown_target_rejected():
    g = _base_graph()
    with pytest.raises(KeyError):
        g.attach_payload(NotePayload(payload_id="pl_x", target_id="n_missing", text="x"))


def test_payloads_for_output_transition():
    g = _base_graph()
    it = InputTransition(input_transition_id="it_1", input_node_ids=("n_a",))
    g.add_input_transition(it)
    ot = OutputTransition(output_transition_id="ot_1", input_transition_id="it_1", to_node_id="n_b")
    g.add_output_transition(ot)
    g.attach_payload(ResultPayload(payload_id="rp_1", target_id="ot_1", status="completed"))
    payloads = g.payloads_for_output_transition("ot_1")
    assert len(payloads) == 1
    assert isinstance(payloads[0], ResultPayload)


def test_roots():
    g = _base_graph()
    it = InputTransition(input_transition_id="it_1", input_node_ids=("n_a",))
    g.add_input_transition(it)
    ot = OutputTransition(output_transition_id="ot_1", input_transition_id="it_1", to_node_id="n_b")
    g.add_output_transition(ot)
    roots = g.roots()
    assert "n_a" in roots
    assert "n_b" not in roots


def test_multi_input_node_transition():
    g = _base_graph()
    g.add_node(Node(node_id="n_c"))
    it = InputTransition(input_transition_id="it_1", input_node_ids=("n_a", "n_b"))
    g.add_input_transition(it)
    ot = OutputTransition(output_transition_id="ot_1", input_transition_id="it_1", to_node_id="n_c")
    g.add_output_transition(ot)
    assert "it_1" in g.input_transitions_from_node["n_a"]
    assert "it_1" in g.input_transitions_from_node["n_b"]
