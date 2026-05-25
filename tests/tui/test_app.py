"""Smoke tests for TUI components (no Textual runtime required)."""

from __future__ import annotations

import re

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
    """type=='transition' now renders transition detail from flowchart click."""
    from stag.tui.detail import build_detail_markdown
    from stag.tui.flowchart import _build_labels
    handle = _make_handle()
    t_id = list(handle.run_graph.transitions)[0]
    state_labels, plan_labels = _build_labels(handle)
    md = build_detail_markdown(handle, {"type": "transition", "id": t_id}, state_labels, plan_labels)
    assert "Transition" in md


def test_build_detail_markdown_node_includes_incoming_section():
    """Non-root node detail should contain an ## Incoming section with transition info."""
    from stag.tui.detail import build_detail_markdown
    from stag.tui.flowchart import _build_labels
    handle = _make_handle()
    graph = handle.run_graph
    # Pick the first non-root node.
    t_id = list(graph.transitions)[0]
    out_node_id = graph.transition_output(t_id)
    state_labels, plan_labels = _build_labels(handle)

    md = build_detail_markdown(
        handle, {"type": "node", "id": out_node_id}, state_labels, plan_labels
    )
    assert "## Incoming" in md
    # Should mention the plan label for the transition.
    pl = plan_labels.get(t_id, "?")
    assert pl in md


# ---------------------------------------------------------------------------
# flowchart.py
# ---------------------------------------------------------------------------


def test_render_flowchart_returns_lines():
    """render_flowchart now returns a tuple (lines, regions)."""
    from stag.tui.flowchart import render_flowchart
    handle = _make_handle()
    result = render_flowchart(handle, handle.root_node_id, depth=2)
    assert isinstance(result, tuple)
    lines, regions = result
    assert isinstance(lines, list)
    assert len(lines) > 0
    assert isinstance(regions, list)


def test_render_flowchart_unknown_center_uses_root():
    from stag.tui.flowchart import render_flowchart
    handle = _make_handle()
    lines, regions = render_flowchart(handle, "n_totally_bogus_id", depth=1)
    assert len(lines) > 0


def test_flowchart_has_connectors():
    """Flowchart for a 2-layer subgraph should contain connector chars (│ or ─)."""
    from stag.tui.flowchart import render_flowchart
    handle = _make_handle()
    lines, _ = render_flowchart(handle, handle.root_node_id, depth=2)
    full_text = "\n".join(lines)
    plain = re.sub(r"\[[^\]]*\]", "", full_text)
    assert "│" in plain or "─" in plain, (
        f"Expected connector chars in flowchart output but found none.\nPlain output:\n{plain}"
    )


def test_flowchart_click_map_covers_nodes():
    """render_flowchart returns click regions that include at least the root node."""
    from stag.tui.flowchart import render_flowchart, ClickRegion
    handle = _make_handle()
    lines, regions = render_flowchart(handle, handle.root_node_id, depth=2)
    assert len(regions) > 0, "Expected at least one click region"
    node_regions = [r for r in regions if r.kind == "node"]
    assert node_regions, "Expected at least one node click region"
    # Root node should appear in the click map.
    root_ids = {r.raw_id for r in node_regions}
    assert handle.root_node_id in root_ids, (
        f"Root node {handle.root_node_id!r} not found in click regions. "
        f"Found: {root_ids}"
    )


def test_flowchart_click_map_covers_transitions():
    """A graph with one transition has a click region for it."""
    from stag.tui.flowchart import render_flowchart, ClickRegion
    handle = _make_handle()
    graph = handle.run_graph
    t_id = list(graph.transitions)[0]
    lines, regions = render_flowchart(handle, handle.root_node_id, depth=2)
    trans_regions = [r for r in regions if r.kind == "transition"]
    assert trans_regions, "Expected at least one transition click region"
    trans_ids = {r.raw_id for r in trans_regions}
    assert t_id in trans_ids, (
        f"Transition {t_id!r} not found in click regions. Found: {trans_ids}"
    )


def test_flowchart_click_region_lookup():
    """Simulate a region lookup by directly querying the click map."""
    from stag.tui.flowchart import render_flowchart
    handle = _make_handle()
    lines, regions = render_flowchart(handle, handle.root_node_id, depth=2)

    # Find the root node region and verify we can look it up by row/col.
    node_regions = [r for r in regions if r.kind == "node" and r.raw_id == handle.root_node_id]
    assert node_regions, "Root node region not found"

    r = node_regions[0]
    # Simulate a click at the center of this region.
    click_x = (r.col_start + r.col_end) // 2
    click_y = r.row

    hit = None
    for region in regions:
        if region.row == click_y and region.col_start <= click_x <= region.col_end:
            hit = region
            break

    assert hit is not None, f"No region matched click at ({click_x}, {click_y})"
    assert hit.kind == "node"
    assert hit.raw_id == handle.root_node_id


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
