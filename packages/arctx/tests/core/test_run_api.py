"""Tests for RunHandle public verbs (step, attach, cut, trace, outcomes)."""

from __future__ import annotations

import pytest

from arctx import init
from arctx.core.cuts import is_active_node
from arctx.core.schema.graph import Step
from arctx.core.schema.payloads import (
    CutPayload,
    NodePayload,
    StepPayload,
)
from arctx.ext.git.payloads import DiffSummary, GitChangePayload
from arctx.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _tp(t_type: str = "experiment") -> StepPayload:
    return StepPayload(payload_id="_", target_id="_", type=t_type)


def _np(text: str = "hello") -> NodePayload:
    return NodePayload(payload_id="_", target_id="_", type="note", content={"text": text})


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_creates_root_node():
    run = init(_req(), run_id="test_init")
    assert run.root_node_id.startswith("n_")
    assert run.root_node_id in run.run_graph.nodes


# ---------------------------------------------------------------------------
# step
# ---------------------------------------------------------------------------


def test_step_creates_single_output():
    run = init(_req())
    t = run.add_step([run.root_node_id], _tp("suggestion"))
    assert isinstance(t, Step)
    assert t.output_node_id in run.run_graph.nodes
    assert t.input_node_ids == (run.root_node_id,)
    payloads = run.run_graph.payloads_for_step(t.step_id)
    assert any(isinstance(p, StepPayload) for p in payloads)


def test_step_multi_input():
    run = init(_req())
    t1 = run.add_step([run.root_node_id], _tp())
    n1 = t1.output_node_id
    t2 = run.add_step([run.root_node_id], _tp())
    n2 = t2.output_node_id

    join = run.add_step([n1, n2], _tp("join"))
    assert set(join.input_node_ids) == {n1, n2}


def test_step_rejects_node_targeting_payload():
    run = init(_req())
    np = NodePayload(payload_id="_", target_id="_", type="note")
    with pytest.raises(ValueError, match="step-targeting"):
        run.add_step([run.root_node_id], np)


def test_step_rejects_unknown_node():
    run = init(_req())
    with pytest.raises(KeyError, match="unknown"):
        run.add_step(["n_bogus"], _tp())


def test_step_rejects_cut_node():
    run = init(_req())
    t1 = run.add_step([run.root_node_id], _tp())
    n1 = t1.output_node_id
    run.cut(n1, target_kind="node")
    with pytest.raises(ValueError, match="cut"):
        run.add_step([n1], _tp())


# ---------------------------------------------------------------------------
# step with an explicit existing output node (connect into an orphan node)
# ---------------------------------------------------------------------------


def test_step_into_existing_output_node():
    run = init(_req())
    orphan = run.add_node()  # standalone node, no producer
    t = run.add_step([run.root_node_id], _tp(), output_node_id=orphan.node_id)
    assert t.output_node_id == orphan.node_id
    assert t.input_node_ids == (run.root_node_id,)
    # No new node was minted: the orphan is now the step's output.
    assert run.run_graph.step_by_output_node[orphan.node_id] == t.step_id


def test_step_into_existing_multi_input():
    run = init(_req())
    a = run.add_step([run.root_node_id], _tp()).output_node_id
    b = run.add_step([run.root_node_id], _tp()).output_node_id
    sink = run.add_node()
    t = run.add_step([a, b], _tp("join"), output_node_id=sink.node_id)
    assert set(t.input_node_ids) == {a, b}
    assert t.output_node_id == sink.node_id


def test_step_output_node_rejects_existing_producer():
    run = init(_req())
    t1 = run.add_step([run.root_node_id], _tp())
    # t1.output_node_id already has a producing step.
    with pytest.raises(ValueError, match="already has a producing step"):
        run.add_step([run.root_node_id], _tp(), output_node_id=t1.output_node_id)


def test_step_output_node_rejects_self_input():
    run = init(_req())
    orphan = run.add_node()
    with pytest.raises(ValueError, match="cannot also be an input"):
        run.add_step([orphan.node_id], _tp(), output_node_id=orphan.node_id)


def test_step_output_node_rejects_cycle():
    run = init(_req())
    # root -> a. Connecting a -> root would close a cycle (root is a's ancestor).
    a = run.add_step([run.root_node_id], _tp()).output_node_id
    with pytest.raises(ValueError, match="cycle"):
        run.add_step([a], _tp(), output_node_id=run.root_node_id)


def test_step_output_node_rejects_unknown():
    run = init(_req())
    with pytest.raises(KeyError, match="unknown output_node_id"):
        run.add_step([run.root_node_id], _tp(), output_node_id="n_bogus")


# ---------------------------------------------------------------------------
# attach
# ---------------------------------------------------------------------------


def test_attach_node_payload():
    run = init(_req())
    returned = run.attach(run.root_node_id, _np("my note"))
    assert isinstance(returned, NodePayload)
    payloads = run.run_graph.payloads_for_node(run.root_node_id)
    assert any(p.payload_id == returned.payload_id for p in payloads)


def test_attach_rejects_step_targeting_payload():
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
    t1 = run.add_step([run.root_node_id], _tp())
    n1 = t1.output_node_id
    cut = run.cut(n1, target_kind="node", reason="stale")
    assert isinstance(cut, CutPayload)
    assert not is_active_node(run.run_graph, n1)


def test_cut_step():
    run = init(_req())
    t1 = run.add_step([run.root_node_id], _tp())
    cut = run.cut(t1.step_id, target_kind="step")
    assert isinstance(cut, CutPayload)


# ---------------------------------------------------------------------------
# GitChangePayload on a step
# ---------------------------------------------------------------------------


def test_git_change_payload_on_step():
    run = init(_req())
    t = run.add_step([run.root_node_id], _tp())
    diff = DiffSummary(files_changed=1, insertions=5, deletions=2)
    git_p = GitChangePayload(
        payload_id="_",
        target_id=t.step_id,
        branch="main",
        head_commit="abc123",
        diff_summary=diff,
    )
    run.run_graph.attach_payload(
        GitChangePayload(
            payload_id=run._next_id("pl"),
            target_id=t.step_id,
            branch="main",
            head_commit="abc123",
            diff_summary=diff,
        )
    )
    payloads = run.run_graph.payloads_for_step(t.step_id)
    assert any(isinstance(p, GitChangePayload) for p in payloads)


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------


def test_trace_returns_history():
    run = init(_req())
    t1 = run.add_step([run.root_node_id], _tp())
    n1 = t1.output_node_id
    ctx = run.trace(n1)
    # Should include the step that produced n1.
    assert t1.step_id in ctx.step_ids


# ---------------------------------------------------------------------------
# outcomes
# ---------------------------------------------------------------------------


def test_outcomes_returns_output_node():
    run = init(_req())
    t1 = run.add_step([run.root_node_id], _tp())
    result = run.outcomes(t1.step_id)
    assert result["output_node_ids"] == [t1.output_node_id]
