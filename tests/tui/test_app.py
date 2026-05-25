"""Smoke tests for TUI components (no Textual runtime required)."""

from __future__ import annotations

import pytest

from stag import init
from stag.core.schema.payloads import NodePayload, TransitionPayload
from stag.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _tp(t_type: str = "experiment") -> TransitionPayload:
    return TransitionPayload(payload_id="_", target_id="_", type=t_type)


def _np(text: str = "hello") -> NodePayload:
    return NodePayload(payload_id="_", target_id="_", type="note", content={"text": text})


def _make_handle():
    run = init(_req(), run_id="tui_test")
    [t1] = run.transition([run.root_node_id], _tp("suggestion"))
    n1 = t1.output_node_id
    run.attach(run.root_node_id, _np("root note"))
    [t2] = run.transition([n1], _tp("implementation"))
    return run


# ---------------------------------------------------------------------------
# detail.py
# ---------------------------------------------------------------------------


def test_build_detail_markdown_node():
    from stag.tui.detail import build_detail_markdown
    handle = _make_handle()
    md = build_detail_markdown(handle, {"type": "node", "id": handle.root_node_id}, {}, {})
    assert "Node" in md or "root" in md


def test_build_detail_markdown_no_data():
    from stag.tui.detail import build_detail_markdown
    handle = _make_handle()
    md = build_detail_markdown(handle, None, {}, {})
    assert "Run Overview" in md


def test_build_detail_markdown_transition():
    from stag.tui.detail import build_detail_markdown
    handle = _make_handle()
    t_id = list(handle.run_graph.transitions)[0]
    md = build_detail_markdown(handle, {"type": "transition", "id": t_id}, {}, {})
    assert "Transition" in md


# ---------------------------------------------------------------------------
# flowchart.py
# ---------------------------------------------------------------------------


def test_render_flowchart_returns_lines():
    from stag.tui.flowchart import render_flowchart
    handle = _make_handle()
    lines = render_flowchart(handle, handle.root_node_id, depth=2)
    assert isinstance(lines, list)
    assert len(lines) > 0


def test_render_flowchart_unknown_center_uses_root():
    from stag.tui.flowchart import render_flowchart
    handle = _make_handle()
    lines = render_flowchart(handle, "n_totally_bogus_id", depth=1)
    assert len(lines) > 0


# ---------------------------------------------------------------------------
# graph_html.py
# ---------------------------------------------------------------------------


def test_render_graph_html():
    from stag.tui.graph_html import render_graph_html
    handle = _make_handle()
    html = render_graph_html(handle)
    assert "<!DOCTYPE html>" in html
    assert handle.run_id in html
    assert "<svg" in html


# ---------------------------------------------------------------------------
# dump.py (sanity check through TUI scenario)
# ---------------------------------------------------------------------------


def test_outline_in_tui_scenario():
    from stag.core.run.dump import DumpOptions, render_outline
    handle = _make_handle()
    out = render_outline(handle, DumpOptions())
    assert "tui_test" in out


def test_mermaid_in_tui_scenario():
    from stag.core.run.dump import DumpOptions, render_mermaid
    handle = _make_handle()
    out = render_mermaid(handle, DumpOptions())
    assert "flowchart TD" in out
