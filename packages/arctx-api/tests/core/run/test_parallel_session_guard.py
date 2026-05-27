"""Unit tests for S9: parallel-session guard (§7.2).

Covers:
- check_branch_tip_consistency raises ParallelSessionConflict when branch tip
  is not in current_node_ids.
- check_branch_tip_consistency passes when tip IS in current_node_ids.
- check_branch_tip_consistency skips when no BranchTipEvent exists yet.
- commit / revert / cherry_pick / merge all reject when another session has
  advanced the branch tip.
"""

from __future__ import annotations

import pytest

from arctx.ext.git.verbs._forward_transition import (
    ParallelSessionConflict,
    check_branch_tip_consistency,
)
from arctx.core.schema.requirements import Requirement
from arctx.core.schema.work_helpers import (
    make_branch_tip_event,
    make_session_pointer_event,
)
import arctx as arctx
from arctx.ext import attach_extensions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handle(run_id: str = "run_psg_test"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return attach_extensions(arctx.init(req, run_id=run_id), ["git"])


def _ensure_session(handle, user_id: str = "user", ws_id: str = "ws_1") -> None:
    handle.ensure_work_session(user_id=user_id, work_session_id=ws_id)


def _advance_branch_tip(handle, *, branch: str, tip_node_id: str, ws_id: str = "ws_other") -> None:
    """Inject a BranchTipEvent directly, simulating another session advancing the tip."""
    # Ensure the session exists before adding a work event that references it.
    handle.ensure_work_session(user_id="other_user", work_session_id=ws_id)
    tip_event = make_branch_tip_event(
        event_id=handle._next_id("we"),
        run_id=handle.run_id,
        work_session_id=ws_id,
        user_id="other_user",
        branch=branch,
        tip_node_id=tip_node_id,
    )
    handle.run_graph.add_work_event(tip_event)


def _set_session_pointer(handle, *, ws_id: str, node_ids: tuple[str, ...], branch: str = "main") -> None:
    """Inject a SessionPointerEvent to set a session's current position."""
    sp_event = make_session_pointer_event(
        event_id=handle._next_id("we"),
        run_id=handle.run_id,
        work_session_id=ws_id,
        user_id="user",
        current_node_ids=node_ids,
        current_branch=branch,
    )
    handle.run_graph.add_work_event(sp_event)


# ---------------------------------------------------------------------------
# Unit tests for check_branch_tip_consistency
# ---------------------------------------------------------------------------

class TestCheckBranchTipConsistency:
    def test_no_branch_tip_event_skips_check(self):
        """First commit on a branch: no BranchTipEvent → no conflict."""
        handle = _make_handle("run_no_tip")
        graph = handle.run_graph
        root = handle.root_node_id
        # No BranchTipEvent at all — should NOT raise.
        check_branch_tip_consistency(graph, "main", (root,))

    def test_tip_in_current_passes(self):
        """Branch tip matches current_node_ids → no conflict."""
        handle = _make_handle("run_tip_match")
        _ensure_session(handle)

        # Do a commit to establish a tip.
        t = handle.git.commit(
            message="first",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="sha1",
            dry_run=True,
        )
        tip_node = t.output_node_id

        # current contains the tip → should NOT raise.
        check_branch_tip_consistency(handle.run_graph, "main", (tip_node,))

    def test_tip_not_in_current_raises(self):
        """Branch tip is not in current_node_ids → ParallelSessionConflict."""
        handle = _make_handle("run_tip_mismatch")
        _ensure_session(handle)

        # session A commits → tip advances to n2.
        t = handle.git.commit(
            message="session A commit",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="sha_a",
            dry_run=True,
        )
        tip_node = t.output_node_id  # n2

        # session B is still at root (n1).
        root = handle.root_node_id

        with pytest.raises(ParallelSessionConflict) as exc_info:
            check_branch_tip_consistency(handle.run_graph, "main", (root,))

        err = exc_info.value
        assert err.branch == "main"
        assert err.expected_tip == tip_node
        assert root in err.current

    def test_tip_in_multi_current_passes(self):
        """Tip is one of multiple current_node_ids (merge case) → no conflict."""
        handle = _make_handle("run_multi_current")
        _ensure_session(handle)

        t = handle.git.commit(
            message="commit",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="sha1",
            dry_run=True,
        )
        tip_node = t.output_node_id
        other_node = handle.root_node_id

        # Tip appears in a multi-input current set.
        check_branch_tip_consistency(
            handle.run_graph, "main", (other_node, tip_node)
        )

    def test_error_message_contains_useful_info(self):
        """ParallelSessionConflict message should mention branch and tip."""
        handle = _make_handle("run_errmsg")
        _advance_branch_tip(handle, branch="feature", tip_node_id="n_fake_tip")

        with pytest.raises(ParallelSessionConflict) as exc_info:
            check_branch_tip_consistency(
                handle.run_graph, "feature", ("n_old",)
            )

        msg = str(exc_info.value)
        assert "feature" in msg
        assert "n_fake_tip" in msg
        assert "arctx pull" in msg.lower() or "pull" in msg.lower()


# ---------------------------------------------------------------------------
# Integration: commit rejects when another session advanced tip
# ---------------------------------------------------------------------------

class TestCommitGuard:
    def test_commit_raises_when_tip_advanced_by_other_session(self):
        """session B cannot commit if session A already moved the branch tip."""
        handle = _make_handle("run_commit_guard")
        _ensure_session(handle, ws_id="ws_a")
        _ensure_session(handle, ws_id="ws_b")

        # Session A commits successfully.
        t_a = handle.git.commit(
            message="session A",
            branch="main",
            user_id="user",
            work_session_id="ws_a",
            head_commit="sha_a",
            dry_run=True,
        )
        # Session B is still at root — tip has advanced to t_a.output_node_id.
        # Session B tries to commit from root.
        _set_session_pointer(handle, ws_id="ws_b", node_ids=(handle.root_node_id,))

        with pytest.raises(ParallelSessionConflict):
            handle.git.commit(
                message="session B conflict",
                branch="main",
                user_id="user",
                work_session_id="ws_b",
                head_commit="sha_b",
                dry_run=True,
            )

    def test_commit_succeeds_after_updating_to_tip(self):
        """session B can commit once it moves its pointer to the current tip."""
        handle = _make_handle("run_commit_after_update")
        _ensure_session(handle, ws_id="ws_a")
        _ensure_session(handle, ws_id="ws_b")

        # Session A commits.
        t_a = handle.git.commit(
            message="session A",
            branch="main",
            user_id="user",
            work_session_id="ws_a",
            head_commit="sha_a",
            dry_run=True,
        )
        tip_node = t_a.output_node_id

        # Session B updates its pointer to the new tip (arctx use <tip>).
        _set_session_pointer(handle, ws_id="ws_b", node_ids=(tip_node,))

        # Session B commits successfully.
        t_b = handle.git.commit(
            message="session B after update",
            branch="main",
            user_id="user",
            work_session_id="ws_b",
            head_commit="sha_b",
            dry_run=True,
        )
        assert t_b.input_node_ids == (tip_node,)

    def test_first_commit_no_guard(self):
        """First commit on a branch (no BranchTipEvent) always passes."""
        handle = _make_handle("run_first_commit")
        _ensure_session(handle)

        # No prior tip — should succeed.
        t = handle.git.commit(
            message="first ever",
            branch="new-branch",
            user_id="user",
            work_session_id="ws_1",
            head_commit="sha_new",
            dry_run=True,
        )
        assert t.transition_id in handle.run_graph.transitions


# ---------------------------------------------------------------------------
# Integration: revert rejects when tip advanced
# ---------------------------------------------------------------------------

class TestRevertGuard:
    def _setup_run_with_reverted_transition(self, run_id: str):
        """Build a run with one commit and return (handle, transition_id)."""
        handle = _make_handle(run_id)
        _ensure_session(handle, ws_id="ws_a")

        t = handle.git.commit(
            message="initial",
            branch="main",
            user_id="user",
            work_session_id="ws_a",
            head_commit="sha1",
            dry_run=True,
        )
        return handle, t.transition_id

    def test_revert_raises_when_tip_advanced(self):
        handle, tid = self._setup_run_with_reverted_transition("run_revert_guard")
        _ensure_session(handle, ws_id="ws_b")

        # session A advances again from its own tip.
        tip_a = handle.run_graph.transitions[tid].output_node_id
        _set_session_pointer(handle, ws_id="ws_a", node_ids=(tip_a,))

        t_a2 = handle.git.commit(
            message="session A second commit",
            branch="main",
            user_id="user",
            work_session_id="ws_a",
            head_commit="sha2",
            dry_run=True,
        )

        # session B is still at root.
        _set_session_pointer(handle, ws_id="ws_b", node_ids=(handle.root_node_id,))

        with pytest.raises(ParallelSessionConflict):
            handle.git.revert(
                target_transition=tid,
                branch="main",
                user_id="user",
                work_session_id="ws_b",
                head_commit="sha_revert",
                dry_run=True,
            )


# ---------------------------------------------------------------------------
# Integration: cherry_pick rejects when tip advanced
# ---------------------------------------------------------------------------

class TestCherryPickGuard:
    def test_cherry_pick_raises_when_tip_advanced(self):
        handle = _make_handle("run_cp_guard")
        _ensure_session(handle, ws_id="ws_a")
        _ensure_session(handle, ws_id="ws_b")

        # Session A commits.
        t_a = handle.git.commit(
            message="session A",
            branch="main",
            user_id="user",
            work_session_id="ws_a",
            head_commit="sha_a",
            dry_run=True,
        )

        # Session B is at root.
        _set_session_pointer(handle, ws_id="ws_b", node_ids=(handle.root_node_id,))

        with pytest.raises(ParallelSessionConflict):
            handle.git.cherry_pick(
                source_sha="deadbeef1234",
                branch="main",
                user_id="user",
                work_session_id="ws_b",
                head_commit="sha_cp",
                dry_run=True,
            )


# ---------------------------------------------------------------------------
# Integration: merge rejects when tip advanced
# ---------------------------------------------------------------------------

class TestMergeGuard:
    def test_merge_raises_when_tip_advanced(self):
        handle = _make_handle("run_merge_guard")
        _ensure_session(handle, ws_id="ws_a")
        _ensure_session(handle, ws_id="ws_b")
        _ensure_session(handle, ws_id="ws_feature")

        # Establish feature branch tip (another node to merge from).
        t_feat = handle.git.commit(
            message="feature commit",
            branch="feature",
            user_id="user",
            work_session_id="ws_feature",
            head_commit="sha_feat",
            dry_run=True,
        )
        feat_node = t_feat.output_node_id

        # Session A advances main.
        _set_session_pointer(handle, ws_id="ws_a", node_ids=(handle.root_node_id,))
        t_a = handle.git.commit(
            message="session A on main",
            branch="main",
            user_id="user",
            work_session_id="ws_a",
            head_commit="sha_a",
            dry_run=True,
        )

        # Session B is still at root — branch tip has advanced.
        _set_session_pointer(handle, ws_id="ws_b", node_ids=(handle.root_node_id,))

        with pytest.raises(ParallelSessionConflict):
            handle.git.merge(
                other_node_id=feat_node,
                branch="main",
                user_id="user",
                work_session_id="ws_b",
                head_commit="sha_merge",
                dry_run=True,
            )
