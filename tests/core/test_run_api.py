"""Tests for RunHandle public verbs (transition, attach, cut, trace, outcomes)."""

from __future__ import annotations

import pytest

from stag import init
from stag.core.cuts import is_active_node
from stag.core.schema.graph import Transition
from stag.core.schema.payloads import (
    CutPayload,
    GitChangePayload,
    DiffSummary,
    NodePayload,
    TransitionPayload,
)
from stag.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _tp(t_type: str = "experiment") -> TransitionPayload:
    return TransitionPayload(payload_id="_", target_id="_", type=t_type)


def _np(text: str = "hello") -> NodePayload:
    return NodePayload(payload_id="_", target_id="_", type="note", content={"text": text})


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_creates_root_node_and_main_view():
    run = init(_req(), run_id="test_init")
    assert run.root_node_id.startswith("n_")
    assert run.root_node_id in run.run_graph.nodes
    assert "main" in run.run_graph.views


# ---------------------------------------------------------------------------
# transition
# ---------------------------------------------------------------------------


def test_transition_max_outcomes_1():
    run = init(_req())
    transitions = run.transition([run.root_node_id], _tp("suggestion"))
    assert len(transitions) == 1
    t = transitions[0]
    assert isinstance(t, Transition)
    assert t.output_node_id in run.run_graph.nodes
    assert t.input_node_ids == (run.root_node_id,)
    payloads = run.run_graph.payloads_for_transition(t.transition_id)
    assert any(isinstance(p, TransitionPayload) for p in payloads)


def test_transition_max_outcomes_3():
    run = init(_req())
    transitions = run.transition([run.root_node_id], _tp(), max_outcomes=3)
    assert len(transitions) == 3
    output_nodes = {t.output_node_id for t in transitions}
    assert len(output_nodes) == 3  # all distinct
    for t in transitions:
        assert t.input_node_ids == (run.root_node_id,)


def test_transition_payload_cloned_per_outcome():
    run = init(_req())
    transitions = run.transition([run.root_node_id], _tp("exp"), max_outcomes=2)
    ids = [
        run.run_graph.payloads_for_transition(t.transition_id)[0].payload_id
        for t in transitions
    ]
    assert ids[0] != ids[1]  # distinct payload_ids


def test_transition_multi_input():
    run = init(_req())
    [t1] = run.transition([run.root_node_id], _tp())
    n1 = t1.output_node_id
    [t2] = run.transition([run.root_node_id], _tp())
    n2 = t2.output_node_id

    [join] = run.transition([n1, n2], _tp("join"))
    assert set(join.input_node_ids) == {n1, n2}


def test_transition_rejects_node_targeting_payload():
    run = init(_req())
    np = NodePayload(payload_id="_", target_id="_", type="note")
    with pytest.raises(ValueError, match="transition-targeting"):
        run.transition([run.root_node_id], np)


def test_transition_rejects_unknown_node():
    run = init(_req())
    with pytest.raises(KeyError, match="unknown"):
        run.transition(["n_bogus"], _tp())


def test_transition_rejects_cut_node():
    run = init(_req())
    [t1] = run.transition([run.root_node_id], _tp())
    n1 = t1.output_node_id
    run.cut(n1, target_kind="node")
    with pytest.raises(ValueError, match="cut"):
        run.transition([n1], _tp())


# ---------------------------------------------------------------------------
# attach
# ---------------------------------------------------------------------------


def test_attach_node_payload():
    run = init(_req())
    returned = run.attach(run.root_node_id, _np("my note"))
    assert isinstance(returned, NodePayload)
    payloads = run.run_graph.payloads_for_node(run.root_node_id)
    assert any(p.payload_id == returned.payload_id for p in payloads)


def test_attach_rejects_transition_targeting_payload():
    run = init(_req())
    tp = _tp()
    with pytest.raises(ValueError, match="node-targeting"):
        run.attach(run.root_node_id, tp)


def test_attach_rejects_unknown_node():
    run = init(_req())
    with pytest.raises(KeyError):
        run.attach("n_bogus", _np())


# ---------------------------------------------------------------------------
# cut
# ---------------------------------------------------------------------------


def test_cut_node():
    run = init(_req())
    [t1] = run.transition([run.root_node_id], _tp())
    n1 = t1.output_node_id
    cut = run.cut(n1, target_kind="node", reason="stale")
    assert isinstance(cut, CutPayload)
    assert not is_active_node(run.run_graph, n1)


def test_cut_transition():
    run = init(_req())
    [t1] = run.transition([run.root_node_id], _tp())
    cut = run.cut(t1.transition_id, target_kind="transition")
    assert isinstance(cut, CutPayload)


# ---------------------------------------------------------------------------
# GitChangePayload on a transition
# ---------------------------------------------------------------------------


def test_git_change_payload_on_transition():
    run = init(_req())
    transitions = run.transition([run.root_node_id], _tp())
    t = transitions[0]
    diff = DiffSummary(files_changed=1, insertions=5, deletions=2)
    git_p = GitChangePayload(
        payload_id="_",
        target_id=t.transition_id,
        branch="main",
        head_commit="abc123",
        diff_summary=diff,
    )
    run.run_graph.attach_payload(
        GitChangePayload(
            payload_id=run._next_id("pl"),
            target_id=t.transition_id,
            branch="main",
            head_commit="abc123",
            diff_summary=diff,
        )
    )
    payloads = run.run_graph.payloads_for_transition(t.transition_id)
    assert any(isinstance(p, GitChangePayload) for p in payloads)


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------


def test_trace_returns_history():
    run = init(_req())
    [t1] = run.transition([run.root_node_id], _tp())
    n1 = t1.output_node_id
    ctx = run.trace(n1)
    # Should include the transition that produced n1.
    assert t1.transition_id in ctx.transition_ids


# ---------------------------------------------------------------------------
# outcomes
# ---------------------------------------------------------------------------


def test_outcomes_returns_output_node():
    run = init(_req())
    [t1] = run.transition([run.root_node_id], _tp())
    result = run.outcomes(t1.transition_id)
    assert result["output_node_ids"] == [t1.output_node_id]
