"""Tests for the dump renderer (outline + mermaid)."""

from __future__ import annotations

from optagent import init
from optagent.core.run.dump import DumpOptions, dump
from optagent.core.schema.payloads import (
    PlanPayload,
    PredictionPayload,
    ResultPayload,
)
from optagent.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _plan(intent: str) -> PlanPayload:
    return PlanPayload(payload_id="pending", target_id="pending", intent=intent)


def _result(metrics=None, status="completed") -> ResultPayload:
    return ResultPayload(
        payload_id="pending",
        target_id="pending",
        status=status,
        metrics=metrics or {},
    )


def _opts(**kw) -> DumpOptions:
    return DumpOptions(**kw)


# ---------- linear chain ---------------------------------------------------


def test_outline_linear_chain():
    run = init(_req(), run_id="t_lin")
    it = run.plan([run.root_node_id], _plan("step1"))
    ot = run.observe(it.input_transition_id, _result({"x": 1.0}))
    it2 = run.plan([ot.to_node_id], _plan("step2"))
    run.observe(it2.input_transition_id, _result({"y": 2.0}))

    out = dump(run, "outline", _opts())
    assert "n_0000" in out
    assert "step1" in out
    assert "step2" in out
    # Each node id should appear exactly once as a primary header (no back-ref)
    assert out.count("↻n_0000") == 0
    # results use → marker
    assert "→" in out


# ---------- predicted branch ----------------------------------------------


def test_outline_predicted_uses_arrow():
    run = init(_req(), run_id="t_pred")
    it = run.plan([run.root_node_id], _plan("guess"))
    run.predict(
        it.input_transition_id,
        payloads=[PredictionPayload(payload_id="pending", target_id="pending")],
    )
    out = dump(run, "outline", _opts())
    assert "⇢" in out


# ---------- multi-input join -----------------------------------------------


def test_outline_join_uses_plus_marker_and_forward_pointer():
    run = init(_req(), run_id="t_join")
    # Two parallel branches off root
    a = run.plan([run.root_node_id], _plan("branchA"))
    a_ot = run.observe(a.input_transition_id, _result())
    b = run.plan([run.root_node_id], _plan("branchB"))
    b_ot = run.observe(b.input_transition_id, _result())
    # Join: input_node_ids[0] = a_ot.to_node, [1] = b_ot.to_node
    j = run.plan([a_ot.to_node_id, b_ot.to_node_id], _plan("merge"))
    run.observe(j.input_transition_id, _result())

    out = dump(run, "outline", _opts())
    # Primary parent gets the transition body with (+...)
    assert f"(+{b_ot.to_node_id})" in out
    # Non-primary parent gets a forward pointer
    assert f"feeds {j.input_transition_id} (@{a_ot.to_node_id})" in out


# ---------- joins index ----------------------------------------------------


def test_outline_joins_index_appears_when_three_or_more():
    run = init(_req(), run_id="t_idx")
    # Create three joins.
    nodes = [run.root_node_id]
    for i in range(3):
        it = run.plan([run.root_node_id], _plan(f"p{i}"))
        ot = run.observe(it.input_transition_id, _result())
        nodes.append(ot.to_node_id)
    # Three multi-input transitions
    for i in range(3):
        it_j = run.plan(
            [nodes[0], nodes[i + 1]], _plan(f"join{i}")
        )
        run.observe(it_j.input_transition_id, _result())

    out = dump(run, "outline", _opts())
    assert "joins (3):" in out


# ---------- cut markers ----------------------------------------------------


def test_outline_cut_marker():
    run = init(_req(), run_id="t_cut")
    it = run.plan([run.root_node_id], _plan("doomed"))
    ot = run.observe(it.input_transition_id, _result())
    run.rewind(ot.output_transition_id, target_kind="output_transition")

    out = dump(run, "outline", _opts())
    assert "✂" in out


# ---------- mermaid format -------------------------------------------------


def test_mermaid_emits_flowchart_and_classes():
    run = init(_req(), run_id="t_mer")
    it = run.plan([run.root_node_id], _plan("step"))
    run.observe(it.input_transition_id, _result({"k": 1.0}))

    out = dump(run, "mermaid", _opts())
    assert out.startswith("```mermaid")
    assert "flowchart TD" in out
    assert "classDef observed" in out
    assert "classDef predicted" in out
    assert out.rstrip().endswith("```")


def test_mermaid_multi_output_uses_diamond_node():
    run = init(_req(), run_id="t_mer_multi")
    it = run.plan([run.root_node_id], _plan("split"))
    run.predict(it.input_transition_id, max_outcomes=2)
    out = dump(run, "mermaid", _opts())
    # multi-output: IT rendered as diamond {{...}}
    assert it.input_transition_id + "{{" in out


# ---------- node note attached --------------------------------------------


def test_outline_renders_node_note():
    run = init(_req(), run_id="t_note")
    it = run.plan([run.root_node_id], _plan("p"))
    ot = run.observe(it.input_transition_id, _result())
    run.note(ot.to_node_id, "key insight")
    out = dump(run, "outline", _opts())
    assert "▸ note: key insight" in out
