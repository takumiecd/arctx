"""Tests for cut cascade logic."""

from __future__ import annotations

import pytest

from arctx import init
from arctx.core.cuts import (
    inactive_node_ids,
    inactive_step_ids,
    is_active_node,
    is_inactive_step,
)
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _tp(t_type: str = "experiment") -> StepPayload:
    return StepPayload(payload_id="_", target_id="_", type=t_type)


def _make_run_with_chain():
    """root -t1-> n1 -t2-> n2"""
    run = init(_req())
    t1 = run.add_step([run.root_node_id], _tp())
    n1 = t1.output_node_id
    t2 = run.add_step([n1], _tp())
    n2 = t2.output_node_id
    return run, t1, n1, t2, n2


def test_no_cuts_all_active():
    run, t1, n1, t2, n2 = _make_run_with_chain()
    assert inactive_node_ids(run.run_graph) == set()
    assert inactive_step_ids(run.run_graph) == set()


def test_cut_step_cascades_to_output_node_and_downstream():
    run, t1, n1, t2, n2 = _make_run_with_chain()
    run.cut(t1.step_id, target_kind="step", reason="bad")

    inactive_n = inactive_node_ids(run.run_graph)
    inactive_t = inactive_step_ids(run.run_graph)

    # t1 is cut, n1 (output) and everything downstream should be inactive.
    assert t1.step_id in inactive_t
    assert n1 in inactive_n
    assert t2.step_id in inactive_t
    assert n2 in inactive_n
    # Root should still be active.
    assert run.root_node_id not in inactive_n


def test_cut_node_cascades_forward():
    run, t1, n1, t2, n2 = _make_run_with_chain()
    run.cut(n1, target_kind="node", reason="stale")

    inactive_n = inactive_node_ids(run.run_graph)
    inactive_t = inactive_step_ids(run.run_graph)

    assert n1 in inactive_n
    assert t2.step_id in inactive_t
    assert n2 in inactive_n
    # t1 (the step that produced n1) is NOT cut just because n1 is cut.
    assert t1.step_id not in inactive_t
    assert run.root_node_id not in inactive_n


def test_is_active_node():
    run, t1, n1, t2, n2 = _make_run_with_chain()
    assert is_active_node(run.run_graph, run.root_node_id)
    run.cut(n1, target_kind="node")
    assert not is_active_node(run.run_graph, n1)


def test_is_inactive_step():
    run, t1, n1, t2, n2 = _make_run_with_chain()
    assert not is_inactive_step(run.run_graph, t1.step_id)
    run.cut(t1.step_id, target_kind="step")
    assert is_inactive_step(run.run_graph, t1.step_id)


def test_cut_already_cut_raises():
    run, t1, n1, t2, n2 = _make_run_with_chain()
    run.cut(t1.step_id, target_kind="step")
    with pytest.raises(ValueError, match="already cut"):
        run.cut(t1.step_id, target_kind="step")


def test_step_into_cut_node_blocked():
    run, t1, n1, t2, n2 = _make_run_with_chain()
    run.cut(n1, target_kind="node")
    with pytest.raises(ValueError, match="cut"):
        run.add_step([n1], _tp())
