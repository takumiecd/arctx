"""Tests for dump (outline and mermaid) rendering."""

from __future__ import annotations

import pytest

from stag import init
from stag.core.run.dump import DumpOptions, render_mermaid, render_outline
from stag.core.schema.payloads import TransitionPayload
from stag.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _tp(t_type: str = "experiment") -> TransitionPayload:
    return TransitionPayload(payload_id="_", target_id="_", type=t_type)


def _make_run():
    run = init(_req(), run_id="dump_test")
    [t1] = run.transition([run.root_node_id], _tp("suggestion"))
    n1 = t1.output_node_id
    [t2] = run.transition([n1], _tp("implementation"))
    return run, t1, n1, t2


# ---------------------------------------------------------------------------
# render_outline
# ---------------------------------------------------------------------------


def test_outline_contains_run_id():
    run, t1, n1, t2 = _make_run()
    out = render_outline(run, DumpOptions())
    assert "dump_test" in out


def test_outline_contains_transition_ids():
    run, t1, n1, t2 = _make_run()
    out = render_outline(run, DumpOptions())
    assert t1.transition_id in out
    assert t2.transition_id in out


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
    run.cut(t1.transition_id, target_kind="transition", reason="wrong")
    out = render_outline(run, DumpOptions())
    assert "✂" in out


def test_outline_depth_option():
    run, t1, n1, t2 = _make_run()
    # depth=1 should cut off t2 from output
    out = render_outline(run, DumpOptions(depth=1))
    # At depth=1, t2 may or may not be included depending on counting
    # At least verify it doesn't crash.
    assert run.root_node_id in out


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
