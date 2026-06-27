"""Tests for RunHandle.git.revert (dry_run=True, no real git required)."""

from __future__ import annotations

import pytest

from arctx.ext.git.payloads import BranchPayload, CherryPickPayload, GitChangePayload, RevertPayload
from arctx.core.schema.work_helpers import latest_branch_tip, latest_lane_pointer
import arctx as arctx
from arctx.ext import attach_extensions
from arctx.core.schema.requirements import Requirement


def _make_handle(run_id: str = "run_test"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return attach_extensions(arctx.init(req, run_id=run_id), ["git"])


def _ensure_session(handle, user_id: str = "user", ws_id: str = "ws_1") -> None:
    handle.ensure_lane(user_id=user_id, lane_id=ws_id)


def _first_commit(handle, sha: str = "sha_orig") -> object:
    """Record a commit step so we have something to revert."""
    _ensure_session(handle)
    return handle.git.commit(
        message="original commit",
        branch="main",
        user_id="user",
        lane_id="ws_1",
        head_commit=sha,
        dry_run=True,
    )


class TestRevertImplDryRun:
    def test_returns_step(self):
        handle = _make_handle()
        orig = _first_commit(handle, sha="sha_orig")

        t = handle.git.revert(
            target_sha="sha_orig",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_revert",
            dry_run=True,
        )
        assert t.step_id in handle.run_graph.steps

    def test_creates_output_node(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_a")
        initial_nodes = set(handle.run_graph.nodes)

        handle.git.revert(
            target_sha="sha_a",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_rev",
            dry_run=True,
        )
        new_nodes = set(handle.run_graph.nodes) - initial_nodes
        assert len(new_nodes) == 1

    def test_revert_payload_attached(self):
        handle = _make_handle()
        orig = _first_commit(handle, sha="sha_orig")

        t = handle.git.revert(
            target_sha="sha_orig",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_revert",
            dry_run=True,
        )
        payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="revert"
        )
        assert len(payloads) == 1
        rp = payloads[0]
        assert isinstance(rp, RevertPayload)
        assert rp.reverted_commit == "sha_orig"
        assert rp.reverted_step == orig.step_id

    def test_git_change_payload_attached(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_orig")

        t = handle.git.revert(
            target_sha="sha_orig",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_rev",
            dry_run=True,
        )
        git_payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="git_change"
        )
        assert len(git_payloads) == 1
        assert isinstance(git_payloads[0], GitChangePayload)
        assert git_payloads[0].head_commit == "sha_rev"

    def test_branch_payload_attached(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_orig")

        t = handle.git.revert(
            target_sha="sha_orig",
            branch="feature/x",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_rev",
            dry_run=True,
        )
        branch_payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="branch"
        )
        assert len(branch_payloads) == 1
        assert isinstance(branch_payloads[0], BranchPayload)
        assert branch_payloads[0].branch == "feature/x"

    def test_original_step_untouched(self):
        """The reverted step must not receive any new payloads."""
        handle = _make_handle()
        orig = _first_commit(handle, sha="sha_orig")

        payloads_before = list(
            handle.run_graph.payloads_by_step.get(orig.step_id, [])
        )

        handle.git.revert(
            target_sha="sha_orig",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_rev",
            dry_run=True,
        )

        payloads_after = list(
            handle.run_graph.payloads_by_step.get(orig.step_id, [])
        )
        assert payloads_before == payloads_after

    def test_lane_pointer_advances(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_orig")

        t = handle.git.revert(
            target_sha="sha_orig",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_rev",
            dry_run=True,
        )
        sp = latest_lane_pointer(handle.run_graph, "ws_1")
        assert sp is not None
        assert t.output_node_id in sp.data["current_node_ids"]

    def test_branch_tip_event(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_orig")

        t = handle.git.revert(
            target_sha="sha_orig",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_rev",
            dry_run=True,
        )
        tip = latest_branch_tip(handle.run_graph, "main")
        assert tip is not None
        assert tip.data["tip_node_id"] == t.output_node_id

    def test_revert_by_step_id(self):
        handle = _make_handle()
        orig = _first_commit(handle, sha="sha_orig2")

        t = handle.git.revert(
            target_step=orig.step_id,
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_rev2",
            dry_run=True,
        )
        payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="revert"
        )
        assert payloads[0].reverted_step == orig.step_id
        assert payloads[0].reverted_commit == "sha_orig2"

    def test_unknown_sha_raises(self):
        handle = _make_handle()
        _ensure_session(handle)

        with pytest.raises(KeyError, match="no arctx step found"):
            handle.git.revert(
                target_sha="nonexistent_sha",
                branch="main",
                head_commit="x",
                dry_run=True,
            )

    def test_unknown_step_id_raises(self):
        handle = _make_handle()
        _ensure_session(handle)

        with pytest.raises(KeyError, match="unknown step_id"):
            handle.git.revert(
                target_step="t_nonexistent",
                branch="main",
                head_commit="x",
                dry_run=True,
            )

    def test_no_args_raises(self):
        handle = _make_handle()
        _ensure_session(handle)

        with pytest.raises(ValueError, match="Either target_sha or target_step"):
            handle.git.revert(dry_run=True)

    def test_both_args_raises(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_x")

        with pytest.raises(ValueError, match="mutually exclusive"):
            handle.git.revert(
                target_sha="sha_x",
                target_step="t_x",
                dry_run=True,
            )

    def test_no_user_id_skips_events(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_noevent")
        initial_events = len(handle.run_graph.work_events)

        handle.git.revert(
            target_sha="sha_noevent",
            branch="main",
            head_commit="sha_rev_no_event",
            dry_run=True,
        )
        # No extra branch_tip / lane_pointer events.
        assert len(handle.run_graph.work_events) == initial_events

    def test_current_sha_is_new_sha(self):
        """After revert, current_sha of the new step must be the revert sha."""
        handle = _make_handle()
        _first_commit(handle, sha="sha_orig3")

        t = handle.git.revert(
            target_sha="sha_orig3",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_revert3",
            dry_run=True,
        )
        assert handle.git.current_sha(t.step_id) == "sha_revert3"
