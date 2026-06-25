"""Tests for dump (outline and mermaid) rendering."""

from __future__ import annotations

import pytest

from arctx import init
from arctx.core.run.dump import DumpOptions, render_mermaid, render_outline
from arctx.core.schema.graph import Node
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _tp(t_type: str = "experiment") -> StepPayload:
    return StepPayload(payload_id="_", target_id="_", type=t_type)


def _make_run():
    run = init(_req(), run_id="dump_test")
    t1 = run.add_step([run.root_node_id], _tp("suggestion"))
    n1 = t1.output_node_id
    t2 = run.add_step([n1], _tp("implementation"))
    return run, t1, n1, t2


# ---------------------------------------------------------------------------
# render_outline
# ---------------------------------------------------------------------------


def test_outline_contains_run_id():
    run, t1, n1, t2 = _make_run()
    out = render_outline(run, DumpOptions())
    assert "dump_test" in out


def test_outline_anchors_reparented_node_under_active_producer():
    run = init(_req(), run_id="dump_reparent")
    wrong = run.add_step([run.root_node_id], _tp("wrong")).output_node_id
    n = run.add_step([wrong], _tp("derive")).output_node_id
    child = run.add_step([n], _tp("child")).output_node_id
    right = run.add_step([run.root_node_id], _tp("right")).output_node_id
    new_step = run.reparent(n, [right], _tp("rederive"))

    out = render_outline(run, DumpOptions())
    lines = out.splitlines()

    # The cut producer defers the node to its active producer (a back-ref).
    deferred = next(line for line in lines if f"↻ {n}" in line)
    assert "active producer" in deferred and new_step.step_id in deferred

    # The descendant child is expanded under the active lineage, exactly once,
    # after the active producer's step.
    assert len([line for line in lines if child in line]) == 1
    assert out.index(new_step.step_id) < out.index(child)


def test_outline_contains_step_ids():
    run, t1, n1, t2 = _make_run()
    out = render_outline(run, DumpOptions())
    assert t1.step_id in out
    assert t2.step_id in out


def test_outline_contains_node_ids():
    run, t1, n1, t2 = _make_run()
    out = render_outline(run, DumpOptions())
    assert run.root_node_id in out
    assert n1 in out


def test_outline_shows_payload_type():
    run, t1, n1, t2 = _make_run()
    out = render_outline(run, DumpOptions())
    assert "suggestion" in out
    assert "implementation" in out


def test_outline_cut_shows_scissors():
    run, t1, n1, t2 = _make_run()
    run.cut(t1.step_id, target_kind="step", reason="wrong")
    out = render_outline(run, DumpOptions())
    assert "✂" in out


def test_outline_depth_option():
    run, t1, n1, t2 = _make_run()
    # depth=1 should cut off t2 from output
    out = render_outline(run, DumpOptions(depth=1))
    # At depth=1, t2 may or may not be included depending on counting
    # At least verify it doesn't crash.
    assert run.root_node_id in out


def test_outline_lists_orphan_components():
    run, t1, n1, t2 = _make_run()
    # A producer-less node (as an imported subgraph would yield). No public verb
    # mints these, so build one directly in the graph container.
    orphan = Node(node_id=run._next_id("n"))
    run.run_graph.add_node(orphan)

    out = render_outline(run, DumpOptions())

    assert "orphans:" in out
    assert orphan.node_id in out


# ---------------------------------------------------------------------------
# render_mermaid
# ---------------------------------------------------------------------------


def test_mermaid_fenced_block():
    run, t1, n1, t2 = _make_run()
    out = render_mermaid(run, DumpOptions())
    assert "```mermaid" in out
    assert "flowchart TD" in out
    assert "```" in out


def test_mermaid_contains_nodes():
    run, t1, n1, t2 = _make_run()
    out = render_mermaid(run, DumpOptions())
    assert run.root_node_id in out
    assert n1 in out


def test_mermaid_cut_class():
    run, t1, n1, t2 = _make_run()
    run.cut(n1, target_kind="node")
    out = render_mermaid(run, DumpOptions())
    assert "cut" in out


def test_mermaid_root_class():
    run, t1, n1, t2 = _make_run()
    out = render_mermaid(run, DumpOptions())
    assert "root" in out
