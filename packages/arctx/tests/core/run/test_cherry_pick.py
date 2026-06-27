"""Tests for RunHandle.git.cherry_pick (dry_run=True, no real git required)."""

from __future__ import annotations

import pytest

from arctx.ext.git.payloads import BranchPayload, CherryPickPayload, GitChangePayload
from arctx.core.schema.work_helpers import latest_branch_tip, latest_lane_pointer
import arctx as arctx
from arctx.ext import attach_extensions
from arctx.core.schema.requirements import Requirement


def _make_handle(run_id: str = "run_test"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return attach_extensions(arctx.init(req, run_id=run_id), ["git"])


def _ensure_session(handle, user_id: str = "user", ws_id: str = "ws_1") -> None:
    handle.ensure_lane(user_id=user_id, lane_id=ws_id)


def _first_commit(handle, sha: str = "sha_src") -> object:
    """Record an original commit so cherry-pick can reference it."""
    _ensure_session(handle)
    return handle.git.commit(
        message="source commit",
        branch="feature",
        user_id="user",
        lane_id="ws_1",
        head_commit=sha,
        dry_run=True,
    )


class TestCherryPickImplDryRun:
    def test_returns_step(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_src1")

        t = handle.git.cherry_pick(
            source_sha="sha_src1",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_cp1",
            dry_run=True,
        )
        assert t.step_id in handle.run_graph.steps

    def test_creates_output_node(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_src2")
        nodes_before = set(handle.run_graph.nodes)

        handle.git.cherry_pick(
            source_sha="sha_src2",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_cp2",
            dry_run=True,
        )
        new_nodes = set(handle.run_graph.nodes) - nodes_before
        assert len(new_nodes) == 1

    def test_cherry_pick_payload_attached(self):
        handle = _make_handle()
        orig = _first_commit(handle, sha="sha_src3")

        t = handle.git.cherry_pick(
            source_sha="sha_src3",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_cp3",
            dry_run=True,
        )
        payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="cherry_pick"
        )
        assert len(payloads) == 1
        cp = payloads[0]
        assert isinstance(cp, CherryPickPayload)
        assert cp.source_commit == "sha_src3"
        assert cp.source_step == orig.step_id

    def test_cherry_pick_payload_source_step_none_for_unknown_sha(self):
        """Cross-repo cherry-pick: source sha not in arctx graph → source_step=None."""
        handle = _make_handle()
        _ensure_session(handle)

        t = handle.git.cherry_pick(
            source_sha="sha_foreign",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_cp_foreign",
            dry_run=True,
        )
        payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="cherry_pick"
        )
        assert payloads[0].source_step is None
        assert payloads[0].source_commit == "sha_foreign"

    def test_git_change_payload_attached(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_src4")

        t = handle.git.cherry_pick(
            source_sha="sha_src4",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_cp4",
            dry_run=True,
        )
        git_payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="git_change"
        )
        assert isinstance(git_payloads[0], GitChangePayload)
        assert git_payloads[0].head_commit == "sha_cp4"

    def test_branch_payload_attached(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_src5")

        t = handle.git.cherry_pick(
            source_sha="sha_src5",
            branch="hotfix",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_cp5",
            dry_run=True,
        )
        branch_payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="branch"
        )
        assert branch_payloads[0].branch == "hotfix"

    def test_lane_pointer_advances(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_src6")

        t = handle.git.cherry_pick(
            source_sha="sha_src6",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_cp6",
            dry_run=True,
        )
        sp = latest_lane_pointer(handle.run_graph, "ws_1")
        assert sp is not None
        assert t.output_node_id in sp.data["current_node_ids"]

    def test_branch_tip_event(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_src7")

        t = handle.git.cherry_pick(
            source_sha="sha_src7",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_cp7",
            dry_run=True,
        )
        tip = latest_branch_tip(handle.run_graph, "main")
        assert tip is not None
        assert tip.data["tip_node_id"] == t.output_node_id

    def test_current_sha_is_new_sha(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_src8")

        t = handle.git.cherry_pick(
            source_sha="sha_src8",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_cp8",
            dry_run=True,
        )
        assert handle.git.current_sha(t.step_id) == "sha_cp8"

    def test_no_user_id_skips_events(self):
        handle = _make_handle()
        _first_commit(handle, sha="sha_noevent")
        initial_events = len(handle.run_graph.work_events)

        handle.git.cherry_pick(
            source_sha="sha_noevent",
            branch="main",
            head_commit="sha_cp_no_event",
            dry_run=True,
        )
        assert len(handle.run_graph.work_events) == initial_events
