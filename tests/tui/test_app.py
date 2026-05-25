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
    t1 = run.transition([run.root_node_id], _tp("suggestion"))
    n1 = t1.output_node_id
    run.attach(run.root_node_id, _np("root note"))
    t2 = run.transition([n1], _tp("implementation"))
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
# editor.py
# ---------------------------------------------------------------------------


def test_editor_parse_json_object():
    from stag.tui.editor import _parse_json_object

    assert _parse_json_object('{"text":"hello"}') == {"text": "hello"}
    assert _parse_json_object("") == {}


def test_editor_parse_json_object_rejects_non_object():
    from stag.tui.editor import _parse_json_object

    with pytest.raises(ValueError):
        _parse_json_object("[1, 2]")


def test_app_has_editor_actions_bound():
    import ast
    import pathlib

    src = pathlib.Path("src/stag/tui/app.py").read_text()
    tree = ast.parse(src)
    method_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    assert "action_create_transition" in method_names
    assert "action_attach_payload" in method_names
    assert "action_cut_selected" in method_names
    assert "action_attach_git_payload" in method_names
    assert '"t"' in src
    assert '"p"' in src
    assert '"c"' in src
    assert '"G"' in src


def test_app_has_auto_refresh_watch_methods():
    import ast
    import pathlib

    src = pathlib.Path("src/stag/tui/app.py").read_text()
    tree = ast.parse(src)
    method_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    assert "_refresh_if_changed" in method_names
    assert "_pull_current_sync_updates" in method_names
    assert "_run_signature" in method_names
    assert "sync_pull" in src
    assert "set_interval" in src
    assert "watch_interval" in src


def test_tui_cli_exposes_watch_flags():
    import pathlib

    src = pathlib.Path("src/stag/cli/commands/tui.py").read_text()

    assert "--watch-interval" in src
    assert "--no-watch" in src


def test_editor_payload_type_options_are_target_compatible():
    from stag.tui.editor import _payload_type_options

    node_values = {value for _, value in _payload_type_options("node", include_cut=True)}
    transition_values = {
        value for _, value in _payload_type_options("transition", include_cut=True)
    }
    transition_create_values = {
        value for _, value in _payload_type_options("transition", include_cut=False)
    }

    assert {"node_payload", "cut"} <= node_values
    assert "transition_payload" not in node_values
    assert {"transition_payload", "cut"} <= transition_values
    assert "node_payload" not in transition_values
    assert "cut" not in transition_create_values


def test_git_payload_form_data():
    from stag.tui.editor import GitPayloadFormData

    data = GitPayloadFormData(transition_id="t_1", commits=("HEAD", "abc123"))
    assert data.transition_id == "t_1"
    assert data.commits == ("HEAD", "abc123")


@pytest.mark.asyncio
async def test_git_payload_shortcut_uses_uppercase_g_key():
    from stag.tui.app import StagApp

    class EmptyStore:
        def list_runs(self):
            return []

    class TestApp(StagApp):
        def __init__(self):
            super().__init__(store=EmptyStore())
            self.git_payload_action_count = 0

        def action_attach_git_payload(self) -> None:
            self.git_payload_action_count += 1

    app = TestApp()
    async with app.run_test() as pilot:
        await pilot.press("G")

    assert app.git_payload_action_count == 1


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


# ---------------------------------------------------------------------------
# Issue 1: node click must not recenter
# ---------------------------------------------------------------------------


def test_node_click_calls_set_selected_not_show():
    """on_flowchart_item_clicked for a node must call set_selected, not show.

    We verify by inspecting the app source: the node-click branch should NOT
    call fv.show(). This is a structural check so it catches regressions without
    needing a running Textual runtime.
    """
    import ast
    import pathlib

    src = pathlib.Path("src/stag/tui/app.py").read_text()
    tree = ast.parse(src)

    # Find on_flowchart_item_clicked method body.
    handler_body_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "on_flowchart_item_clicked":
            handler_body_src = ast.unparse(node)
            break

    assert handler_body_src is not None, "on_flowchart_item_clicked not found in app.py"

    # The handler must call set_selected.
    assert "set_selected" in handler_body_src, (
        "on_flowchart_item_clicked must call fv.set_selected() for node clicks"
    )

    # The handler must NOT branch on event.kind == "node" to call fv.show().
    # Specifically: fv.show(..., event.raw_id) after an isinstance/kind check should be absent.
    # We look for fv.show being called inside an if-branch that checks event.kind.
    # A simpler proxy: the string 'fv.show' must not appear in the handler body.
    assert "fv.show" not in handler_body_src, (
        "on_flowchart_item_clicked must not call fv.show() — node click should only set_selected"
    )


# ---------------------------------------------------------------------------
# Issues 2 & 3: junction glyphs must be correct for 1->2 branch
# ---------------------------------------------------------------------------


def _make_branching_handle():
    """Root -> T1 -> N1, Root -> T2 -> N2 — two transitions from root."""
    from stag import init
    from stag.core.schema.payloads import TransitionPayload
    from stag.core.schema.requirements import Requirement

    req = Requirement(requirement_id="r", target_type="task", target_id="t")
    run = init(req, run_id="branch_test")
    tp = lambda t: TransitionPayload(payload_id="_", target_id="_", type=t)

    # Two separate transitions from root produce two children at the same layer.
    t1 = run.transition([run.root_node_id], tp("left"))
    t2 = run.transition([run.root_node_id], tp("right"))
    return run


def test_flowchart_junctions_use_proper_glyphs():
    """When a node fans out to two transitions, connector junction must use ┴/┬/┌/┐, not └/┘ mid-line."""
    from stag.tui.flowchart import render_flowchart

    handle = _make_branching_handle()
    lines, _ = render_flowchart(handle, handle.root_node_id, depth=2)
    plain = re.sub(r"\[[^\]]*\]", "", "\n".join(lines))

    # There must be horizontal connector characters somewhere (we have at least one
    # non-straight connection in a fan-out topology when items are in different columns).
    has_horizontal = "─" in plain
    has_junction = any(ch in plain for ch in ("┴", "┬", "┌", "┐", "┼", "├", "┤"))

    if has_horizontal:
        # If there is a horizontal segment, there must also be proper corner/junction glyphs.
        assert has_junction, (
            f"Horizontal connector found but no junction glyphs (┴┬┌┐┼├┤). "
            f"Likely a bare └ or ┘ in the middle of a horizontal run.\nPlain:\n{plain}"
        )

    # There must be no standalone └ or ┘ at a position that has a horizontal
    # neighbour on BOTH sides (that would be a T-junction rendered as a corner).
    for line in plain.splitlines():
        for i, ch in enumerate(line):
            if ch in ("└", "┘"):
                left_has_horiz = i > 0 and line[i - 1] == "─"
                right_has_horiz = i < len(line) - 1 and line[i + 1] == "─"
                assert not (left_has_horiz and right_has_horiz), (
                    f"Found {ch!r} at col {i} with '─' on both sides — should be ┴ or ┬.\n"
                    f"Line: {line!r}"
                )
