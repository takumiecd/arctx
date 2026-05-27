"""Tests for git branch membership queries."""

from __future__ import annotations

import pytest

from arctx.core.run_graph import RunGraph
from arctx.core.schema.graph import Node, Transition
from arctx.core.schema.work import WorkSession
from arctx.core.schema.work_helpers import make_branch_tip_event
from arctx.ext.git.queries import branch_members


def _node(graph: RunGraph, node_id: str) -> Node:
    n = Node(node_id=node_id)
    graph.add_node(n)
    return n


def _transition(graph: RunGraph, t_id: str, inputs: list[str], output: str) -> Transition:
    t = Transition(
        transition_id=t_id,
        input_node_ids=tuple(inputs),
        output_node_id=output,
    )
    graph.add_transition(t)
    return t


def _add_session(graph: RunGraph, session_id: str = "ws_1") -> None:
    session = WorkSession(
        work_session_id=session_id,
        run_id="run_1",
        user_id="user",
    )
    graph.add_work_session(session)


def _add_branch_tip(graph: RunGraph, branch: str, tip_node_id: str, event_id: str) -> None:
    ev = make_branch_tip_event(
        event_id=event_id,
        run_id="run_1",
        work_session_id="ws_1",
        user_id="user",
        branch=branch,
        tip_node_id=tip_node_id,
    )
    graph.add_work_event(ev)


class TestBranchMembers:
    def test_empty_when_no_tip_event(self):
        graph = RunGraph()
        _node(graph, "n_root")
        assert branch_members(graph, "main") == set()

    def test_single_node_tip(self):
        """When the tip is the root (no ancestors), members = {tip}."""
        graph = RunGraph()
        _node(graph, "n_root")
        _add_session(graph)
        _add_branch_tip(graph, "main", "n_root", "we_1")

        members = branch_members(graph, "main")
        assert members == {"n_root"}

    def test_chain_includes_all_ancestors(self):
        graph = RunGraph()
        _node(graph, "n_0")
        _node(graph, "n_1")
        _node(graph, "n_2")
        _transition(graph, "t_1", ["n_0"], "n_1")
        _transition(graph, "t_2", ["n_1"], "n_2")

        _add_session(graph)
        _add_branch_tip(graph, "main", "n_2", "we_1")

        members = branch_members(graph, "main")
        assert members == {"n_0", "n_1", "n_2"}

    def test_latest_tip_wins(self):
        graph = RunGraph()
        _node(graph, "n_0")
        _node(graph, "n_1")
        _node(graph, "n_2")
        _transition(graph, "t_1", ["n_0"], "n_1")
        _transition(graph, "t_2", ["n_1"], "n_2")

        _add_session(graph)
        _add_branch_tip(graph, "main", "n_1", "we_1")
        _add_branch_tip(graph, "main", "n_2", "we_2")

        # Latest tip is n_2 → members should include n_0, n_1, n_2.
        members = branch_members(graph, "main")
        assert members == {"n_0", "n_1", "n_2"}

    def test_different_branches_are_independent(self):
        graph = RunGraph()
        _node(graph, "n_root")
        _node(graph, "n_main_tip")
        _node(graph, "n_dev_tip")
        _transition(graph, "t_m", ["n_root"], "n_main_tip")
        _transition(graph, "t_d", ["n_root"], "n_dev_tip")

        _add_session(graph)
        _add_branch_tip(graph, "main", "n_main_tip", "we_m")
        _add_branch_tip(graph, "dev", "n_dev_tip", "we_d")

        main_members = branch_members(graph, "main")
        dev_members = branch_members(graph, "dev")

        assert "n_main_tip" in main_members
        assert "n_root" in main_members
        assert "n_dev_tip" not in main_members

        assert "n_dev_tip" in dev_members
        assert "n_root" in dev_members
        assert "n_main_tip" not in dev_members

    def test_unknown_branch_returns_empty(self):
        graph = RunGraph()
        _node(graph, "n_root")
        _add_session(graph)
        _add_branch_tip(graph, "main", "n_root", "we_1")

        assert branch_members(graph, "no-such-branch") == set()
