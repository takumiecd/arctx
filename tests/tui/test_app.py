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
# Minimal mock Tree for populate_dag_tree tests (no Textual install needed).
# ---------------------------------------------------------------------------

class _MockTreeNode:
    """Mimics the subset of Textual TreeNode used by populate_dag_tree."""

    def __init__(self, label: str = "", data=None):
        self.label = label
        self.data = data
        self.children: list[_MockTreeNode] = []

    def add(self, label: str, data=None) -> "_MockTreeNode":
        child = _MockTreeNode(label, data)
        self.children.append(child)
        return child

    def add_leaf(self, label: str, data=None) -> "_MockTreeNode":
        child = _MockTreeNode(label, data)
        self.children.append(child)
        return child


class _MockTree:
    """Mimics the subset of Textual Tree used by populate_dag_tree."""

    def __init__(self):
        self.root = _MockTreeNode("root")

    def clear(self):
        self.root.children.clear()


def _walk_tree(node: _MockTreeNode):
    """Yield all nodes in the mock tree (depth-first)."""
    yield node
    for child in node.children:
        yield from _walk_tree(child)


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


def test_build_detail_markdown_transition_falls_back_to_overview():
    """type=='transition' is no longer a selectable row; should fall through to overview."""
    from stag.tui.detail import build_detail_markdown
    handle = _make_handle()
    t_id = list(handle.run_graph.transitions)[0]
    # 'transition' kind is no longer dispatched — falls back to _run_overview.
    md = build_detail_markdown(handle, {"type": "transition", "id": t_id}, {}, {})
    assert "Run Overview" in md


def test_build_detail_markdown_node_includes_incoming_section():
    """Non-root node detail should contain an ## Incoming section with transition info."""
    from stag.tui.detail import build_detail_markdown
    from stag.tui.dag_tree import _build_labels
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
# dag_tree.py — new structure tests
# ---------------------------------------------------------------------------


def test_tree_no_standalone_transition_rows():
    """After populate_dag_tree, no TreeNode should have data['type'] == 'transition'."""
    from stag.tui.dag_tree import populate_dag_tree
    handle = _make_handle()
    mock_tree = _MockTree()
    populate_dag_tree(mock_tree, handle)

    for node in _walk_tree(mock_tree.root):
        if node.data is not None:
            assert node.data.get("type") != "transition", (
                f"Found standalone transition row: {node.label!r} data={node.data}"
            )


def test_tree_includes_transition_label_in_node_row():
    """Each non-root node row's label should contain the plan label (e.g. 'P1')."""
    from stag.tui.dag_tree import populate_dag_tree, _build_labels
    handle = _make_handle()
    _, plan_labels = _build_labels(handle)

    mock_tree = _MockTree()
    populate_dag_tree(mock_tree, handle)

    # Collect all node-type rows (excluding the virtual tree root wrapper).
    node_rows = [
        n for n in _walk_tree(mock_tree.root)
        if n.data is not None and n.data.get("type") == "node"
        and n.data.get("id") != handle.root_node_id
    ]
    assert node_rows, "Expected at least one non-root node row"

    # Each non-root node row label should contain a plan label like 'P1'.
    plan_label_values = set(plan_labels.values())
    for row in node_rows:
        label = row.label
        found = any(pl in label for pl in plan_label_values)
        assert found, f"Node row label {label!r} contains no plan label (expected one of {plan_label_values})"


def test_tree_root_has_no_incoming_label():
    """The root node row should say '(root)' and NOT contain '→'."""
    from stag.tui.dag_tree import populate_dag_tree
    handle = _make_handle()
    mock_tree = _MockTree()
    populate_dag_tree(mock_tree, handle)

    root_rows = [
        n for n in _walk_tree(mock_tree.root)
        if n.data is not None and n.data.get("id") == handle.root_node_id
    ]
    assert root_rows, "Root node row not found"
    root_label = root_rows[0].label
    assert "root" in root_label
    assert "→" not in root_label


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


def test_flowchart_has_connectors():
    """Flowchart for a 2-layer subgraph should contain connector chars (│ or ─)."""
    from stag.tui.flowchart import render_flowchart
    handle = _make_handle()
    # depth=2 gives root → transition → child node (3 layers → connectors between them)
    lines = render_flowchart(handle, handle.root_node_id, depth=2)
    full_text = "\n".join(lines)
    # Strip Rich markup tags to inspect plain chars.
    import re
    plain = re.sub(r"\[[^\]]*\]", "", full_text)
    assert "│" in plain or "─" in plain, (
        f"Expected connector chars in flowchart output but found none.\nPlain output:\n{plain}"
    )


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
