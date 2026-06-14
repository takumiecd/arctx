"""Tests for RunGraph.ancestors_of."""

from __future__ import annotations

import pytest

from arctx.core.run_graph import RunGraph
from arctx.core.schema.graph import Node, Step


def _node(graph: RunGraph, node_id: str) -> Node:
    n = Node(node_id=node_id)
    graph.add_node(n)
    return n


def _step(graph: RunGraph, t_id: str, inputs: list[str], output: str) -> Step:
    t = Step(
        step_id=t_id,
        input_node_ids=tuple(inputs),
        output_node_id=output,
    )
    graph.add_step(t)
    return t


class TestAncestorsOf:
    def test_no_ancestors_for_root(self):
        graph = RunGraph()
        _node(graph, "n_root")
        assert graph.ancestors_of("n_root") == set()

    def test_simple_chain(self):
        graph = RunGraph()
        _node(graph, "n_0")
        _node(graph, "n_1")
        _node(graph, "n_2")
        _step(graph, "t_1", ["n_0"], "n_1")
        _step(graph, "t_2", ["n_1"], "n_2")

        assert graph.ancestors_of("n_2") == {"n_0", "n_1"}
        assert graph.ancestors_of("n_1") == {"n_0"}
        assert graph.ancestors_of("n_0") == set()

    def test_multi_input_step(self):
        """Node with multi-input step should include both parent branches."""
        graph = RunGraph()
        _node(graph, "n_a")
        _node(graph, "n_b")
        _node(graph, "n_merge")
        _step(graph, "t_merge", ["n_a", "n_b"], "n_merge")

        ancs = graph.ancestors_of("n_merge")
        assert ancs == {"n_a", "n_b"}

    def test_diamond_dag(self):
        """Common ancestor should appear once."""
        graph = RunGraph()
        _node(graph, "n_root")
        _node(graph, "n_left")
        _node(graph, "n_right")
        _node(graph, "n_merge")

        _step(graph, "t_l", ["n_root"], "n_left")
        _step(graph, "t_r", ["n_root"], "n_right")
        _step(graph, "t_m", ["n_left", "n_right"], "n_merge")

        ancs = graph.ancestors_of("n_merge")
        assert ancs == {"n_root", "n_left", "n_right"}

    def test_long_chain(self):
        """ancestors_of should walk back all the way to the root."""
        graph = RunGraph()
        N = 5
        for i in range(N + 1):
            _node(graph, f"n_{i}")
        for i in range(N):
            _step(graph, f"t_{i}", [f"n_{i}"], f"n_{i+1}")

        ancs = graph.ancestors_of(f"n_{N}")
        assert ancs == {f"n_{i}" for i in range(N)}

    def test_node_not_in_graph(self):
        """ancestors_of on an unknown node returns empty set (no KeyError)."""
        graph = RunGraph()
        _node(graph, "n_0")
        # n_unknown is not in graph; step_by_output_node won't have it
        ancs = graph.ancestors_of("n_unknown")
        assert ancs == set()
