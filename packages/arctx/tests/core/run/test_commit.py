"""Tests for RunHandle.git.commit (dry_run=True, no real git required)."""

from __future__ import annotations

import pytest

from arctx.core.run_graph import RunGraph
from arctx.core.schema.graph import Node
from arctx.ext.git.payloads import BranchPayload, GitChangePayload
from arctx.core.schema.requirements import Requirement
from arctx.core.schema.work import WorkSession
from arctx.core.schema.work_helpers import (
    SESSION_POINTER_EVENT,
    BRANCH_TIP_EVENT,
    latest_branch_tip,
    latest_session_pointer,
    make_session_pointer_event,
)
import arctx as arctx
from arctx.ext import attach_extensions


def _make_handle(run_id: str = "run_test"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    handle = attach_extensions(arctx.init(req, run_id=run_id), ["git"])
    return handle


def _ensure_session(handle, user_id: str = "user", ws_id: str = "ws_1") -> None:
    handle.ensure_work_session(user_id=user_id, work_session_id=ws_id)


class TestCommitImplDryRun:
    def test_returns_step(self):
        handle = _make_handle()
        _ensure_session(handle)
        t = handle.git.commit(
            message="test commit",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="abc123",
            dry_run=True,
        )
        assert t.step_id in handle.run_graph.steps

    def test_creates_output_node(self):
        handle = _make_handle()
        _ensure_session(handle)
        initial_nodes = set(handle.run_graph.nodes)
        handle.git.commit(
            message="test commit",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="abc123",
            dry_run=True,
        )
        new_nodes = set(handle.run_graph.nodes) - initial_nodes
        assert len(new_nodes) == 1

    def test_branch_payload_attached(self):
        handle = _make_handle()
        _ensure_session(handle)
        t = handle.git.commit(
            message="test commit",
            branch="feature/x",
            user_id="user",
            work_session_id="ws_1",
            head_commit="abc123",
            dry_run=True,
        )
        branch_payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="branch"
        )
        assert len(branch_payloads) == 1
        assert isinstance(branch_payloads[0], BranchPayload)
        assert branch_payloads[0].branch == "feature/x"

    def test_git_change_payload_attached(self):
        handle = _make_handle()
        _ensure_session(handle)
        t = handle.git.commit(
            message="test commit",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="deadbeef",
            dry_run=True,
        )
        git_payloads = handle.run_graph.payloads_for_step(
            t.step_id, payload_type="git_change"
        )
        assert len(git_payloads) == 1
        assert isinstance(git_payloads[0], GitChangePayload)
        assert git_payloads[0].head_commit == "deadbeef"
        assert git_payloads[0].branch == "main"

    def test_branch_tip_event_appended(self):
        handle = _make_handle()
        _ensure_session(handle)
        t = handle.git.commit(
            message="test commit",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="abc",
            dry_run=True,
        )
        tip_event = latest_branch_tip(handle.run_graph, "main")
        assert tip_event is not None
        assert tip_event.data["tip_node_id"] == t.output_node_id

    def test_session_pointer_event_appended(self):
        handle = _make_handle()
        _ensure_session(handle)
        t = handle.git.commit(
            message="test commit",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="abc",
            dry_run=True,
        )
        sp = latest_session_pointer(handle.run_graph, "ws_1")
        assert sp is not None
        assert t.output_node_id in sp.data["current_node_ids"]

    def test_session_pointer_advances_current(self):
        """After commit, the session pointer should point to the new output node."""
        handle = _make_handle()
        _ensure_session(handle)

        # First commit.
        t1 = handle.git.commit(
            message="first",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="sha1",
            dry_run=True,
        )

        # Second commit should start from t1's output node.
        t2 = handle.git.commit(
            message="second",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="sha2",
            dry_run=True,
        )
        assert t1.output_node_id in t2.input_node_ids

    def test_uses_root_node_when_no_session_pointer(self):
        """Without a prior session pointer, commit starts from root."""
        handle = _make_handle()
        _ensure_session(handle)
        root_id = handle.root_node_id

        t = handle.git.commit(
            message="first commit from root",
            branch="main",
            user_id="user",
            work_session_id="ws_1",
            head_commit="sha_root",
            dry_run=True,
        )
        assert root_id in t.input_node_ids

    def test_no_user_id_skips_events(self):
        """When user_id is None, no work events should be recorded."""
        handle = _make_handle()
        initial_event_count = len(handle.run_graph.work_events)

        handle.git.commit(
            message="no session",
            branch="main",
            head_commit="abc",
            dry_run=True,
        )
        # No events added because user_id=None.
        assert len(handle.run_graph.work_events) == initial_event_count

    def test_consecutive_commits_form_chain(self):
        """Each commit's input should be the previous commit's output."""
        handle = _make_handle()
        _ensure_session(handle)

        prev_output = handle.root_node_id
        for i in range(3):
            t = handle.git.commit(
                message=f"commit {i}",
                branch="main",
                user_id="user",
                work_session_id="ws_1",
                head_commit=f"sha_{i}",
                dry_run=True,
            )
            assert prev_output in t.input_node_ids
            prev_output = t.output_node_id
