"""Tests for cut/inactive computation over CutPayloads."""

from __future__ import annotations

from optagent.core.cuts import (
    cut_input_transition_ids,
    cut_output_transition_ids,
    inactive_node_ids,
    inactive_output_transition_ids,
    is_active_node,
    is_inactive_output_transition,
)
from optagent.core.run_graph import RunGraph
from optagent.core.schema.graph import InputTransition, Node, OutputTransition
from optagent.core.schema.payloads import CutPayload, ResultPayload


def _linear_graph() -> RunGraph:
    """n_a → (it1) → ot1 → n_b → (it2) → ot2 → n_c"""
    g = RunGraph()
    for nid in ("n_a", "n_b", "n_c"):
        g.add_node(Node(node_id=nid))

    it1 = InputTransition(input_transition_id="it_1", input_node_ids=("n_a",))
    g.add_input_transition(it1)
    ot1 = OutputTransition(output_transition_id="ot_1", input_transition_id="it_1", to_node_id="n_b")
    g.add_output_transition(ot1)
    g.attach_payload(ResultPayload(payload_id="rp_1", target_id="ot_1", status="completed"))

    it2 = InputTransition(input_transition_id="it_2", input_node_ids=("n_b",))
    g.add_input_transition(it2)
    ot2 = OutputTransition(output_transition_id="ot_2", input_transition_id="it_2", to_node_id="n_c")
    g.add_output_transition(ot2)
    g.attach_payload(ResultPayload(payload_id="rp_2", target_id="ot_2", status="completed"))

    return g


def test_no_cuts_means_empty_sets():
    g = _linear_graph()
    assert cut_input_transition_ids(g) == set()
    assert cut_output_transition_ids(g) == set()
    assert inactive_output_transition_ids(g) == set()
    assert inactive_node_ids(g) == set()


def test_cut_on_input_transition_makes_all_its_ots_inactive():
    g = _linear_graph()
    g.attach_payload(
        CutPayload(
            payload_id="cp_1",
            target_id="it_1",
            target_kind="input_transition",
            cut_at="2026-01-01T00:00:00Z",
        )
    )
    assert "it_1" in cut_input_transition_ids(g)
    assert "ot_1" in inactive_output_transition_ids(g)
    assert is_inactive_output_transition(g, "ot_1")
    # n_b and n_c become inactive (reachable from ot_1)
    assert "n_b" in inactive_node_ids(g)
    assert "n_c" in inactive_node_ids(g)
    # ot_2 is also inactive because it starts from cut n_b
    assert "ot_2" in inactive_output_transition_ids(g)
    # n_a remains active
    assert is_active_node(g, "n_a")


def test_cut_on_output_transition_only_that_ot_inactive():
    g = _linear_graph()
    g.attach_payload(
        CutPayload(
            payload_id="cp_2",
            target_id="ot_1",
            target_kind="output_transition",
            cut_at="2026-01-01T00:00:00Z",
        )
    )
    assert "ot_1" in cut_output_transition_ids(g)
    assert is_inactive_output_transition(g, "ot_1")
    # n_b and downstream become inactive
    assert not is_active_node(g, "n_b")
    assert not is_active_node(g, "n_c")
    # n_a still active
    assert is_active_node(g, "n_a")
    # it_1 itself is not cut (only its output was)
    assert "it_1" not in cut_input_transition_ids(g)
