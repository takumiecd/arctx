"""Tests for RunHandle.merge (dry_run=True, no real git required)."""

from __future__ import annotations

import pytest

from stag.core.schema.graph import Node
from stag.core.schema.payloads import GitChangePayload, MergePayload, JoinPayload
from stag.core.schema.requirements import Requirement
from stag.core.schema.work_helpers import (
    BRANCH_TIP_EVENT,
    SESSION_POINTER_EVENT,
    latest_branch_tip,
    latest_session_pointer,
    make_branch_tip_event,
    make_session_pointer_event,
)
import stag


def _make_handle(run_id: str = "run_merge_test"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return stag.init(req, run_id=run_id)


def _ensure_session(handle, user_id: str = "user", ws_id: str = "ws_1") -> None:
    handle.ensure_work_session(user_id=user_id, work_session_id=ws_id)


def _make_two_branch_run():
    """Build a run with two independent branches from root.

    Returns (handle, n_root, n1, n2, t1, t2) where:
      - n_root → t1 → n1  (main branch, ws_1 tracks this)
      - n_root → t2 → n2  (feature branch, different session)
    """
    handle = _make_handle("run_two_branch")
    _ensure_session(handle, user_id="user", ws_id="ws_main")
    _ensure_session(handle, user_id="user", ws_id="ws_feature")

    n_root = handle.root_node_id

    # Advance main branch.
    t1 = handle.commit(
        message="main commit",
        branch="main",
        user_id="user",
        work_session_id="ws_main",
        head_commit="sha_main",
        dry_run=True,
    )
    n1 = t1.output_node_id

    # Advance feature branch from root (not from n1).
    # We need to set session pointer to root for ws_feature first.
    sp_event = make_session_pointer_event(
        event_id=handle._next_id("we"),
        run_id=handle.run_id,
        work_session_id="ws_feature",
        user_id="user",
        current_node_ids=(n_root,),
        current_branch="feature",
    )
    handle.run_graph.add_work_event(sp_event)

    t2 = handle.commit(
        message="feature commit",
        branch="feature",
        user_id="user",
        work_session_id="ws_feature",
        head_commit="sha_feature",
        dry_run=True,
    )
    n2 = t2.output_node_id

    return handle, n_root, n1, n2, t1, t2


class TestMergeImplDryRun:
    def test_creates_multi_input_transition(self):
        handle, n_root, n1, n2, t1, t2 = _make_two_branch_run()

        merge_t = handle.merge(
            other_node_id=n2,
            branch="main",
            user_id="user",
            work_session_id="ws_main",
            head_commit="sha_merge",
            dry_run=True,
        )
        assert len(merge_t.input_node_ids) == 2
        assert n1 in merge_t.input_node_ids
        assert n2 in merge_t.input_node_ids

    def test_merge_payload_attached(self):
        handle, n_root, n1, n2, t1, t2 = _make_two_branch_run()

        merge_t = handle.merge(
            other_node_id=n2,
            branch="main",
            user_id="user",
            work_session_id="ws_main",
            head_commit="sha_merge",
            dry_run=True,
        )
        merge_payloads = handle.run_graph.payloads_for_transition(
            merge_t.transition_id, payload_type="merge"
        )
        assert len(merge_payloads) == 1
        assert isinstance(merge_payloads[0], MergePayload)
        assert merge_payloads[0].merged_into == "main"

    def test_git_change_payload_attached(self):
        handle, n_root, n1, n2, t1, t2 = _make_two_branch_run()

        merge_t = handle.merge(
            other_node_id=n2,
            branch="main",
            user_id="user",
            work_session_id="ws_main",
            head_commit="sha_merge_commit",
            dry_run=True,
        )
        git_payloads = handle.run_graph.payloads_for_transition(
            merge_t.transition_id, payload_type="git_change"
        )
        assert len(git_payloads) == 1
        assert isinstance(git_payloads[0], GitChangePayload)
        assert git_payloads[0].head_commit == "sha_merge_commit"

    def test_branch_tip_event_updated(self):
        handle, n_root, n1, n2, t1, t2 = _make_two_branch_run()

        merge_t = handle.merge(
            other_node_id=n2,
            branch="main",
            user_id="user",
            work_session_id="ws_main",
            head_commit="sha_merge",
            dry_run=True,
        )
        tip_event = latest_branch_tip(handle.run_graph, "main")
        assert tip_event is not None
        assert tip_event.data["tip_node_id"] == merge_t.output_node_id

    def test_session_pointer_advances(self):
        handle, n_root, n1, n2, t1, t2 = _make_two_branch_run()

        merge_t = handle.merge(
            other_node_id=n2,
            branch="main",
            user_id="user",
            work_session_id="ws_main",
            head_commit="sha_merge",
            dry_run=True,
        )
        sp = latest_session_pointer(handle.run_graph, "ws_main")
        assert sp is not None
        assert merge_t.output_node_id in sp.data["current_node_ids"]
        # After merge, should be a single output node.
        assert sp.data["current_node_ids"] == [merge_t.output_node_id]

    def test_join_true_records_join_payload(self):
        handle, n_root, n1, n2, t1, t2 = _make_two_branch_run()

        join_t = handle.merge(
            other_node_id=n2,
            branch="main",
            user_id="user",
            work_session_id="ws_main",
            head_commit="sha_join",
            dry_run=True,
            join=True,
        )
        join_payloads = handle.run_graph.payloads_for_transition(
            join_t.transition_id, payload_type="join"
        )
        assert len(join_payloads) == 1
        assert isinstance(join_payloads[0], JoinPayload)
        # MergePayload should NOT be present.
        merge_payloads = handle.run_graph.payloads_for_transition(
            join_t.transition_id, payload_type="merge"
        )
        assert len(merge_payloads) == 0

    def test_join_false_no_join_payload(self):
        handle, n_root, n1, n2, t1, t2 = _make_two_branch_run()

        merge_t = handle.merge(
            other_node_id=n2,
            branch="main",
            user_id="user",
            work_session_id="ws_main",
            head_commit="sha_merge2",
            dry_run=True,
            join=False,
        )
        join_payloads = handle.run_graph.payloads_for_transition(
            merge_t.transition_id, payload_type="join"
        )
        assert len(join_payloads) == 0

    def test_resolve_other_node_via_branch_tip_event(self):
        """other_node_id resolution from BranchTipEvent when other_branch is given."""
        handle = _make_handle("run_tip_resolve")
        _ensure_session(handle, ws_id="ws_main")
        _ensure_session(handle, ws_id="ws_feat")

        n_root = handle.root_node_id

        # Advance main.
        t_main = handle.commit(
            message="main", branch="main",
            user_id="user", work_session_id="ws_main",
            head_commit="sha_m", dry_run=True,
        )

        # Advance feature from root.
        sp = make_session_pointer_event(
            event_id=handle._next_id("we"),
            run_id=handle.run_id,
            work_session_id="ws_feat",
            user_id="user",
            current_node_ids=(n_root,),
            current_branch="feature",
        )
        handle.run_graph.add_work_event(sp)

        t_feat = handle.commit(
            message="feat", branch="feature",
            user_id="user", work_session_id="ws_feat",
            head_commit="sha_f", dry_run=True,
        )

        # Merge using other_branch name — resolves via BranchTipEvent.
        merge_t = handle.merge(
            other_branch="feature",
            branch="main",
            user_id="user",
            work_session_id="ws_main",
            head_commit="sha_merged",
            dry_run=True,
        )
        assert t_feat.output_node_id in merge_t.input_node_ids

    def test_no_other_raises_value_error(self):
        handle = _make_handle("run_no_other")
        _ensure_session(handle)
        with pytest.raises(ValueError, match="other_node_id or other_branch"):
            handle.merge(dry_run=True)

    def test_unknown_branch_raises_value_error(self):
        handle = _make_handle("run_unknown_branch")
        _ensure_session(handle)
        with pytest.raises(ValueError, match="no BranchTipEvent found"):
            handle.merge(other_branch="nonexistent", dry_run=True)

    def test_no_user_id_skips_events(self):
        handle, n_root, n1, n2, t1, t2 = _make_two_branch_run()
        initial_event_count = len(handle.run_graph.work_events)

        handle.merge(
            other_node_id=n2,
            branch="main",
            head_commit="sha_no_user",
            dry_run=True,
            # user_id and work_session_id are None
        )
        # No BranchTipEvent or SessionPointerEvent should be added.
        new_events = handle.run_graph.work_events[initial_event_count:]
        new_typed = [e for e in new_events if e.event_type in (SESSION_POINTER_EVENT, BRANCH_TIP_EVENT)]
        assert len(new_typed) == 0

    def test_merge_creates_output_node(self):
        handle, n_root, n1, n2, t1, t2 = _make_two_branch_run()
        initial_nodes = set(handle.run_graph.nodes)

        merge_t = handle.merge(
            other_node_id=n2,
            branch="main",
            user_id="user",
            work_session_id="ws_main",
            head_commit="sha_merge",
            dry_run=True,
        )
        new_nodes = set(handle.run_graph.nodes) - initial_nodes
        assert len(new_nodes) == 1
        assert list(new_nodes)[0] == merge_t.output_node_id

    def test_merge_transition_not_in_input_twice(self):
        """other_node_id must not appear in input_node_ids twice even if current=other."""
        handle = _make_handle("run_dedup")
        _ensure_session(handle, ws_id="ws_x")

        # Commit once.
        t = handle.commit(
            message="first", branch="main",
            user_id="user", work_session_id="ws_x",
            head_commit="sha_1", dry_run=True,
        )
        n_out = t.output_node_id

        # Try to merge current node into itself — should deduplicate inputs.
        merge_t = handle.merge(
            other_node_id=n_out,
            branch="main",
            user_id="user",
            work_session_id="ws_x",
            head_commit="sha_merge_self",
            dry_run=True,
        )
        # Should have only one input (deduplicated).
        assert merge_t.input_node_ids.count(n_out) == 1
