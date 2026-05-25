"""Tests for the STAG TUI."""

from __future__ import annotations

import pytest

from stag import init
from stag.core.schema.payloads import PlanPayload, PredictionPayload, ResultPayload
from stag.core.schema.requirements import Requirement


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _req(rid: str = "req-tui") -> Requirement:
    return Requirement(requirement_id=rid, target_type="task", target_id="tui-test")


def _plan_payload(intent: str = "test plan") -> PlanPayload:
    return PlanPayload(payload_id="pending", target_id="pending", intent=intent)


def _result(status: str = "completed") -> ResultPayload:
    return ResultPayload(payload_id="pending", target_id="pending", status=status)


def _build_simple_run():
    """root -> P1 -> S1 (observed); P1 also has 2 predicted outputs S2, S3."""
    run = init(_req(), run_id="tui-test-run")
    t1 = run.plan([run.root_node_id], _plan_payload("heuristic X"))
    pred_nodes = run.predict(t1.transition_id, max_outcomes=2)
    obs_node = run.observe(t1.transition_id, _result("completed"))
    return run, t1, pred_nodes, obs_node


class _FakeStore:
    """Minimal in-memory store stub for TUI tests."""

    def __init__(self, handles: list):
        self._handles = {h.run_id: h for h in handles}

    def list_runs(self) -> list[dict]:
        return [{"run_id": rid} for rid in self._handles]

    def load_run(self, run_id: str):
        return self._handles[run_id]

    def run_path(self, run_id: str):
        from pathlib import Path
        return Path(f"/tmp/fake/{run_id}")


# ---------------------------------------------------------------------------
# Unit tests — no app.run_test required
# ---------------------------------------------------------------------------

def test_build_labels_root_is_s0():
    run, *_ = _build_simple_run()
    from stag.tui.dag_tree import _build_labels
    sl, pl = _build_labels(run)
    assert sl[run.root_node_id] == "S0"


def test_build_labels_plan_sequential():
    run, t1, _, _ = _build_simple_run()
    from stag.tui.dag_tree import _build_labels
    _, pl = _build_labels(run)
    assert pl[t1.transition_id] == "P1"


def test_detail_node_no_raw_id():
    run, t1, pred_nodes, obs_node = _build_simple_run()
    from stag.tui.dag_tree import _build_labels
    from stag.tui.detail import build_detail_markdown
    sl, pl = _build_labels(run)
    md = build_detail_markdown(run, {"type": "node", "id": run.root_node_id}, sl, pl)
    # No raw IDs (prefixed with n_ or t_ or pl_) in output.
    assert "n_" not in md
    assert "t_" not in md
    assert "pl_" not in md
    assert "S0" in md


def test_detail_transition_no_raw_id():
    run, t1, _, _ = _build_simple_run()
    from stag.tui.dag_tree import _build_labels
    from stag.tui.detail import build_detail_markdown
    sl, pl = _build_labels(run)
    md = build_detail_markdown(run, {"type": "transition", "id": t1.transition_id}, sl, pl)
    assert "n_" not in md
    assert "t_" not in md
    assert "P1" in md
    assert "heuristic X" in md


def test_detail_backref_node():
    run, *_ = _build_simple_run()
    from stag.tui.dag_tree import _build_labels
    from stag.tui.detail import build_detail_markdown
    sl, pl = _build_labels(run)
    md = build_detail_markdown(run, {"type": "backref", "id": run.root_node_id}, sl, pl)
    assert "S0" in md
    assert "n_" not in md


def test_detail_forward_pointer():
    run, t1, _, _ = _build_simple_run()
    from stag.tui.dag_tree import _build_labels
    from stag.tui.detail import build_detail_markdown
    sl, pl = _build_labels(run)
    md = build_detail_markdown(run, {"type": "forward_pointer", "id": t1.transition_id}, sl, pl)
    assert "P1" in md
    assert "t_" not in md


def test_detail_empty_returns_run_overview():
    run, *_ = _build_simple_run()
    from stag.tui.dag_tree import _build_labels
    from stag.tui.detail import build_detail_markdown
    sl, pl = _build_labels(run)
    md = build_detail_markdown(run, None, sl, pl)
    assert "Overview" in md or "Run" in md
    assert "n_" not in md


def test_detail_section_type_returns_overview():
    run, *_ = _build_simple_run()
    from stag.tui.dag_tree import _build_labels
    from stag.tui.detail import build_detail_markdown
    sl, pl = _build_labels(run)
    md = build_detail_markdown(run, {"type": "section", "id": ""}, sl, pl)
    assert "n_" not in md


# ---------------------------------------------------------------------------
# Tree population tests
# ---------------------------------------------------------------------------

def test_populate_dag_tree_root_label_contains_s0():
    from textual.widgets import Tree
    run, *_ = _build_simple_run()
    tree = Tree("root")
    state_labels, _ = populate_tree_and_get_labels(tree, run)
    # Walk all tree nodes to find one whose label text contains S0 and root.
    all_labels = _collect_labels(tree.root)
    s0_root_labels = [l for l in all_labels if "S0" in l and "root" in l]
    assert s0_root_labels, f"No S0+root label found in tree. Labels: {all_labels[:10]}"


def test_populate_dag_tree_node_data_has_type_and_id():
    from textual.widgets import Tree
    run, *_ = _build_simple_run()
    tree = Tree("root")
    populate_tree_and_get_labels(tree, run)
    all_data = _collect_data(tree.root)
    for data in all_data:
        if data is not None:
            assert "type" in data, f"Missing 'type' in node data: {data}"
            assert "id" in data, f"Missing 'id' in node data: {data}"


def populate_tree_and_get_labels(tree, run):
    from stag.tui.dag_tree import populate_dag_tree
    state_labels, plan_labels = populate_dag_tree(tree, run)
    return state_labels, plan_labels


def _collect_labels(node) -> list[str]:
    results = [str(node.label)]
    for child in node.children:
        results.extend(_collect_labels(child))
    return results


def _collect_data(node) -> list:
    results = [node.data]
    for child in node.children:
        results.extend(_collect_data(child))
    return results


# ---------------------------------------------------------------------------
# Flowchart tests
# ---------------------------------------------------------------------------

def test_render_flowchart_single_node_has_box_chars():
    run = init(_req("fc-single"), run_id="fc-single")
    from stag.tui.flowchart import render_flowchart
    lines = render_flowchart(run, run.root_node_id, depth=1)
    joined = "\n".join(lines)
    assert "┌" in joined or "S0" in joined, f"Expected box or S0 in: {joined!r}"


def test_render_flowchart_single_node_contains_s0():
    run = init(_req("fc-s0"), run_id="fc-s0")
    from stag.tui.flowchart import render_flowchart
    lines = render_flowchart(run, run.root_node_id, depth=1)
    joined = "\n".join(lines)
    assert "S0" in joined


def test_render_flowchart_plan_and_outputs_contains_labels():
    run, t1, pred_nodes, _ = _build_simple_run()
    from stag.tui.flowchart import render_flowchart
    from stag.tui.dag_tree import _build_labels
    sl, pl = _build_labels(run)
    lines = render_flowchart(run, run.root_node_id, depth=2)
    joined = "\n".join(lines)
    # Should contain the plan label P1.
    assert "P1" in joined, f"P1 not in flowchart output:\n{joined}"


def test_render_flowchart_depth_affects_output():
    run, t1, pred_nodes, obs_node = _build_simple_run()
    # Add a second plan off the observed node.
    t2 = run.plan([obs_node.node_id], _plan_payload("second plan"))
    run.predict(t2.transition_id, max_outcomes=1)
    from stag.tui.flowchart import render_flowchart
    lines_d1 = render_flowchart(run, run.root_node_id, depth=1)
    lines_d3 = render_flowchart(run, run.root_node_id, depth=3)
    # Deeper should have more content.
    assert len("\n".join(lines_d3)) >= len("\n".join(lines_d1))


# ---------------------------------------------------------------------------
# graph_html tests
# ---------------------------------------------------------------------------

def test_render_graph_html_contains_svg():
    run, *_ = _build_simple_run()
    from stag.tui.graph_html import render_graph_html
    html = render_graph_html(run)
    assert "<svg" in html


def test_render_graph_html_contains_s0():
    run, *_ = _build_simple_run()
    from stag.tui.graph_html import render_graph_html
    html = render_graph_html(run)
    assert "S0" in html


def test_render_graph_html_no_raw_ids():
    run, *_ = _build_simple_run()
    from stag.tui.graph_html import render_graph_html
    html = render_graph_html(run)
    # Raw node/transition IDs should not appear (they're opaque hashes).
    # We check that the run_id (which is controlled) appears but n_<uuid> style don't bleed through.
    # Since IDs are opaque (n_<uuid>), scan for the n_ prefix inside the SVG body.
    svg_start = html.index("<svg")
    svg_body = html[svg_start:]
    assert "n_" not in svg_body, f"Raw node ID leaked into SVG"


# ---------------------------------------------------------------------------
# App integration tests (using run_test)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_runs_list_populated():
    from stag.tui.app import StagApp
    run, *_ = _build_simple_run()
    store = _FakeStore([run])
    app = StagApp(store=store)
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await pilot.pause()
        lv = app.query_one("#runs-list")
        # Should have one item for our run.
        assert len(lv.children) == 1


@pytest.mark.asyncio
async def test_app_selecting_run_populates_tree():
    from stag.tui.app import StagApp
    run, *_ = _build_simple_run()
    store = _FakeStore([run])
    app = StagApp(store=store)
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await pilot.pause()
        # The app auto-selects the first run on mount.
        tree = app.query_one("#dag-tree")
        labels = _collect_labels(tree.root)
        s0_labels = [l for l in labels if "S0" in l]
        assert s0_labels, f"S0 not found in tree after mount. Labels: {labels[:10]}"


@pytest.mark.asyncio
async def test_app_toggle_flowchart_shows_and_hides():
    from stag.tui.app import StagApp
    run, *_ = _build_simple_run()
    store = _FakeStore([run])
    app = StagApp(store=store)
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await pilot.pause()
        # App auto-selects first run on mount.
        md = app.query_one("#detail-markdown")
        fv = app.query_one("#flowchart-view")
        # Initially markdown visible, flowchart hidden.
        assert md.display is True
        assert fv.display is False

        # Toggle flowchart on.
        await pilot.press("m")
        await pilot.pause()
        assert md.display is False
        assert fv.display is True

        # Toggle back.
        await pilot.press("m")
        await pilot.pause()
        assert md.display is True
        assert fv.display is False
