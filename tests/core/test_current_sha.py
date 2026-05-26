"""Tests for RunGraph.current_sha and RunGraph.transition_by_sha."""

from __future__ import annotations

import pytest

from stag.core.run_graph import RunGraph
from stag.core.schema.graph import Node, Transition
from stag.core.schema.payloads import DiffSummary, GitChangePayload


def _make_graph_with_transition() -> tuple[RunGraph, str]:
    """Return a RunGraph and one transition_id."""
    g = RunGraph()
    n0 = Node(node_id="n_root")
    n1 = Node(node_id="n_out")
    g.add_node(n0)
    g.add_node(n1)
    t = Transition(
        transition_id="t_1",
        input_node_ids=("n_root",),
        output_node_id="n_out",
    )
    g.add_transition(t)
    return g, "t_1"


def _git_payload(g: RunGraph, t_id: str, pl_id: str, sha: str) -> GitChangePayload:
    p = GitChangePayload(
        payload_id=pl_id,
        target_id=t_id,
        branch="main",
        head_commit=sha,
        diff_summary=DiffSummary(0, 0, 0),
    )
    g.attach_payload(p)
    return p


class TestCurrentSha:
    def test_no_git_change_payload_returns_none(self):
        g, t_id = _make_graph_with_transition()
        assert g.current_sha(t_id) is None

    def test_single_git_change_payload(self):
        g, t_id = _make_graph_with_transition()
        _git_payload(g, t_id, "pl_1", "abc123")
        assert g.current_sha(t_id) == "abc123"

    def test_multiple_git_change_payloads_returns_latest(self):
        g, t_id = _make_graph_with_transition()
        _git_payload(g, t_id, "pl_1", "sha_old")
        _git_payload(g, t_id, "pl_2", "sha_new")
        # current_sha should be the last-appended one.
        assert g.current_sha(t_id) == "sha_new"

    def test_three_payloads_returns_last(self):
        g, t_id = _make_graph_with_transition()
        for i, sha in enumerate(["sha_a", "sha_b", "sha_c"]):
            _git_payload(g, t_id, f"pl_{i}", sha)
        assert g.current_sha(t_id) == "sha_c"

    def test_unknown_transition_returns_none(self):
        g, _ = _make_graph_with_transition()
        assert g.current_sha("t_nonexistent") is None


class TestTransitionBySha:
    def test_not_found_returns_none(self):
        g, t_id = _make_graph_with_transition()
        assert g.transition_by_sha("deadbeef") is None

    def test_found_returns_transition_id(self):
        g, t_id = _make_graph_with_transition()
        _git_payload(g, t_id, "pl_1", "cafecafe")
        assert g.transition_by_sha("cafecafe") == t_id

    def test_after_amend_old_sha_not_found(self):
        g, t_id = _make_graph_with_transition()
        _git_payload(g, t_id, "pl_1", "old_sha")
        _git_payload(g, t_id, "pl_2", "new_sha")
        # current_sha is now new_sha; old_sha no longer matches current.
        assert g.transition_by_sha("old_sha") is None
        assert g.transition_by_sha("new_sha") == t_id

    def test_multiple_transitions_returns_latest(self):
        """When two transitions somehow share a sha, return the last inserted."""
        g = RunGraph()
        n0 = Node(node_id="n0")
        n1 = Node(node_id="n1")
        n2 = Node(node_id="n2")
        g.add_node(n0)
        g.add_node(n1)
        g.add_node(n2)

        t1 = Transition(
            transition_id="t_first",
            input_node_ids=("n0",),
            output_node_id="n1",
        )
        t2 = Transition(
            transition_id="t_second",
            input_node_ids=("n1",),
            output_node_id="n2",
        )
        g.add_transition(t1)
        g.add_transition(t2)

        sha = "shared_sha"
        _git_payload(g, "t_first", "pl_a", sha)
        _git_payload(g, "t_second", "pl_b", sha)

        # Both have current_sha == shared_sha; transition_by_sha returns the last
        # one visited (most-recently-created, i.e. t_second).
        result = g.transition_by_sha(sha)
        assert result == "t_second"
