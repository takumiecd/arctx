"""Tests for RunHandle.git.reset (dry_run=True, no real git required)."""

from __future__ import annotations

import pytest

from arctx.core.cuts import is_inactive_step
from arctx.core.schema.payloads import CutPayload
from arctx.core.schema.requirements import Requirement
from arctx.core.schema.work_helpers import (
    RESET_EVENT,
    SESSION_POINTER_EVENT,
    latest_session_pointer,
)
import arctx as arctx
from arctx.ext import attach_extensions


def _make_handle(run_id: str = "run_test"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return attach_extensions(arctx.init(req, run_id=run_id), ["git"])


def _ensure_session(handle, user_id: str = "user", ws_id: str = "ws_1") -> None:
    handle.ensure_lane(user_id=user_id, lane_id=ws_id)


def _make_chain(handle, length: int = 3):
    """Build root -> t1 -> n1 -> t2 -> n2 -> ... and return (steps, nodes).

    Returns list of steps and list of output nodes in order.
    """
    _ensure_session(handle)
    steps = []
    nodes = []
    for i in range(length):
        t = handle.git.commit(
            message=f"commit {i+1}",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit=f"sha_{i+1}",
            dry_run=True,
        )
        steps.append(t)
        nodes.append(t.output_node_id)
    return steps, nodes


class TestResetImplDryRun:
    def test_no_new_step_created(self):
        """reset must NOT create a new Step."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        count_before = len(handle.run_graph.steps)

        handle.git.reset(
            to_node_id=nodes[0],  # n1
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        assert len(handle.run_graph.steps) == count_before

    def test_no_new_node_created(self):
        """reset must NOT create a new Node."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        count_before = len(handle.run_graph.nodes)

        handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        assert len(handle.run_graph.nodes) == count_before

    def test_reset_event_recorded(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)

        events_before = [e for e in handle.run_graph.work_events if e.event_type == RESET_EVENT]

        handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        reset_events = [e for e in handle.run_graph.work_events if e.event_type == RESET_EVENT]
        assert len(reset_events) == len(events_before) + 1

    def test_reset_event_data(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        # current is n3 (nodes[2]), resetting to n1 (nodes[0])

        handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        reset_event = next(
            e for e in reversed(handle.run_graph.work_events)
            if e.event_type == RESET_EVENT
        )
        assert reset_event.data["to_node_id"] == nodes[0]
        assert reset_event.data["mode"] == "hard"

    def test_session_pointer_updated(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)

        handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        sp = latest_session_pointer(handle.run_graph, "ws_1")
        assert sp is not None
        assert nodes[0] in sp.data["current_node_ids"]

    def test_session_pointer_event_appended(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)

        sp_events_before = [
            e for e in handle.run_graph.work_events
            if e.event_type == SESSION_POINTER_EVENT
        ]

        handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        sp_events_after = [
            e for e in handle.run_graph.work_events
            if e.event_type == SESSION_POINTER_EVENT
        ]
        assert len(sp_events_after) == len(sp_events_before) + 1

    def test_hard_mode_cuts_discarded_steps(self):
        """mode=hard: t2 and t3 should be cut."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        t1, t2, t3 = steps

        handle.git.reset(
            to_node_id=nodes[0],  # n1 — so t2 and t3 are discarded
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        assert is_inactive_step(handle.run_graph, t2.step_id)
        assert is_inactive_step(handle.run_graph, t3.step_id)

    def test_hard_mode_t1_not_cut(self):
        """mode=hard: t1 (leading to to_node) must NOT be cut."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        t1, t2, t3 = steps

        handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        assert not is_inactive_step(handle.run_graph, t1.step_id)

    def test_mixed_mode_no_cut(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        t1, t2, t3 = steps

        handle.git.reset(
            to_node_id=nodes[0],
            mode="mixed",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        assert not is_inactive_step(handle.run_graph, t2.step_id)
        assert not is_inactive_step(handle.run_graph, t3.step_id)

    def test_soft_mode_no_cut(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        t1, t2, t3 = steps

        handle.git.reset(
            to_node_id=nodes[0],
            mode="soft",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        assert not is_inactive_step(handle.run_graph, t2.step_id)
        assert not is_inactive_step(handle.run_graph, t3.step_id)

    def test_cut_payload_on_discarded_steps(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        t2, t3 = steps[1], steps[2]

        handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        cut_payloads = [
            p for p in handle.run_graph.payloads.values()
            if isinstance(p, CutPayload) and p.target_kind == "step"
        ]
        cut_ids = {p.target_id for p in cut_payloads}
        assert t2.step_id in cut_ids
        assert t3.step_id in cut_ids

    def test_return_value_structure(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=2)

        result = handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        assert "to_node_id" in result
        assert "from_node_id" in result
        assert "discarded_step_ids" in result
        assert "mode" in result
        assert "event_id" in result
        assert result["to_node_id"] == nodes[0]
        assert result["mode"] == "hard"

    def test_return_discarded_ids_correct(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        t2, t3 = steps[1], steps[2]

        result = handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        discarded = set(result["discarded_step_ids"])
        assert t2.step_id in discarded
        assert t3.step_id in discarded

    def test_to_node_not_ancestor_raises(self):
        """Resetting to a node that is not an ancestor must raise ValueError."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=2)
        # nodes[1] is current (n2); nodes[0] is n1, root is the real ancestor.
        # Try resetting "forward" — root is an ancestor of n1, not the reverse.
        # Create a second branch from the root to get a non-ancestor node.
        req = Requirement(requirement_id="req2", target_type="task", target_id="t2")
        other = attach_extensions(arctx.init(req, run_id="run_other"), ["git"])
        other.ensure_lane(user_id="u", lane_id="ws_o")
        other_t = other.git.commit(
            message="other",
            branch="main",
            user_id="u",
            lane_id="ws_o",
            head_commit="sha_o",
            dry_run=True,
        )
        # The other run's node has no relationship to handle's nodes.
        # But we can just use an unrelated node within the same handle.
        # The simplest non-ancestor: nodes[0] is the parent of nodes[1],
        # so nodes[1] is NOT an ancestor of nodes[0] — resetting from n1 to n2 would fail.
        # Currently current is nodes[1]. Let's make current = nodes[0] and try to reset to nodes[1].
        # But reset requires going backwards, so forward is the violation.
        # Reset current=nodes[1] to a node not in ancestors_of(nodes[1]).
        # We'll inject a fresh node directly.
        from arctx.core.schema.graph import Node
        alien = Node(node_id="n_alien")
        handle.run_graph.add_node(alien)

        with pytest.raises(ValueError, match="not an ancestor"):
            handle.git.reset(
                to_node_id="n_alien",
                mode="hard",
                user_id="user",
                lane_id="ws_1",
                dry_run=True,
            )

    def test_same_node_no_op(self):
        """Resetting to the current node produces no discarded steps."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=2)

        result = handle.git.reset(
            to_node_id=nodes[1],  # same as current
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        assert result["discarded_step_ids"] == []

    def test_no_user_id_skips_events(self):
        """Without user_id, no WorkEvents are recorded."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=2)
        event_count_before = len(handle.run_graph.work_events)

        # Pass lane_id so from_node is resolved correctly,
        # but omit user_id so no work events should be written.
        result = handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            lane_id="ws_1",
            dry_run=True,
        )
        assert len(handle.run_graph.work_events) == event_count_before
        assert result["event_id"] is None

    def test_hard_mode_no_double_cut(self):
        """If a step is already cut, reset should not raise."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        t2 = steps[1]

        # Pre-cut t2.
        handle.cut(t2.step_id, target_kind="step", reason="pre-cut")

        # reset should not raise even though t2 is already cut.
        handle.git.reset(
            to_node_id=nodes[0],
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        # t3 must be cut by reset (t2 was already cut before).
        assert is_inactive_step(handle.run_graph, steps[2].step_id)

    def test_to_sha_lookup(self):
        """to_sha is resolved via step_by_sha -> output_node_id."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        # sha_1 corresponds to t1 (nodes[0])
        result = handle.git.reset(
            to_sha="sha_1",
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        assert result["to_node_id"] == nodes[0]

    def test_to_sha_unknown_raises(self):
        handle = _make_handle()
        _make_chain(handle, length=2)

        with pytest.raises(KeyError, match="no arctx step found"):
            handle.git.reset(
                to_sha="nonexistent_sha",
                mode="hard",
                dry_run=True,
            )

    def test_no_args_raises(self):
        handle = _make_handle()
        _make_chain(handle, length=1)

        with pytest.raises(ValueError, match="Either to_node_id or to_sha"):
            handle.git.reset(mode="hard", dry_run=True)

    def test_both_args_raises(self):
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=1)

        with pytest.raises(ValueError, match="mutually exclusive"):
            handle.git.reset(
                to_node_id=nodes[0],
                to_sha="sha_1",
                mode="hard",
                dry_run=True,
            )

    def test_reset_to_middle_node(self):
        """Resetting from n3 to n2 discards only t3."""
        handle = _make_handle()
        steps, nodes = _make_chain(handle, length=3)
        t1, t2, t3 = steps

        result = handle.git.reset(
            to_node_id=nodes[1],  # n2
            mode="hard",
            user_id="user",
            lane_id="ws_1",
            dry_run=True,
        )
        discarded = set(result["discarded_step_ids"])
        assert t3.step_id in discarded
        assert t2.step_id not in discarded
        assert t1.step_id not in discarded

        assert is_inactive_step(handle.run_graph, t3.step_id)
        assert not is_inactive_step(handle.run_graph, t2.step_id)
