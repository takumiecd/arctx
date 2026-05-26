"""Tests for RunHandle.adopt_rewrite (amend/rebase sha tracking)."""

from __future__ import annotations

import pytest

import stag
from stag.core.schema.payloads import GitChangePayload
from stag.core.schema.requirements import Requirement
from stag.core.schema.work_helpers import AMEND_EVENT, REBASE_EVENT


def _make_handle(run_id: str = "run_rewrite"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return stag.init(req, run_id=run_id)


def _commit(handle, sha: str, branch: str = "main", ws: str = "ws") -> str:
    """Helper: do a dry_run commit and return the transition_id."""
    handle.ensure_work_session(user_id="user", work_session_id=ws)
    t = handle.commit(
        message=f"commit {sha}",
        branch=branch,
        user_id="user",
        work_session_id=ws,
        head_commit=sha,
        dry_run=True,
    )
    return t.transition_id


class TestAdoptRewriteAmend:
    def test_amend_appends_new_git_change_payload(self):
        handle = _make_handle()
        t_id = _commit(handle, "sha_before")

        result = handle.adopt_rewrite(
            sha_map={"sha_before": "sha_after"},
            onto="sha_after",
            mode="amend",
            user_id="user",
            work_session_id="ws",
        )

        assert t_id in result["affected_transitions"]
        assert "sha_before" not in result["skipped_shas"]

    def test_amend_current_sha_updates(self):
        handle = _make_handle()
        t_id = _commit(handle, "sha_v1")

        handle.adopt_rewrite(
            sha_map={"sha_v1": "sha_v2"},
            onto="sha_v2",
            mode="amend",
            user_id="user",
            work_session_id="ws",
        )

        assert handle.run_graph.current_sha(t_id) == "sha_v2"

    def test_amend_preserves_history(self):
        """Old GitChangePayload is still present; new one is appended."""
        handle = _make_handle()
        t_id = _commit(handle, "sha_old")

        handle.adopt_rewrite(
            sha_map={"sha_old": "sha_new"},
            onto="sha_new",
            mode="amend",
            user_id="user",
            work_session_id="ws",
        )

        git_payloads = handle.run_graph.payloads_for_transition(
            t_id, payload_type="git_change"
        )
        assert len(git_payloads) == 2
        shas = [p.head_commit for p in git_payloads]  # type: ignore[attr-defined]
        assert "sha_old" in shas
        assert "sha_new" in shas

    def test_amend_records_amend_event(self):
        handle = _make_handle()
        _commit(handle, "sha_a")

        result = handle.adopt_rewrite(
            sha_map={"sha_a": "sha_b"},
            onto="sha_b",
            mode="amend",
            user_id="user",
            work_session_id="ws",
        )

        event_ids = [e.event_id for e in handle.run_graph.work_events]
        assert result["event_id"] in event_ids

        amend_events = [
            e for e in handle.run_graph.work_events if e.event_type == AMEND_EVENT
        ]
        assert len(amend_events) == 1
        assert amend_events[0].data["old_sha"] == "sha_a"
        assert amend_events[0].data["new_sha"] == "sha_b"

    def test_amend_unknown_sha_goes_to_skipped(self):
        handle = _make_handle()
        _commit(handle, "sha_known")

        result = handle.adopt_rewrite(
            sha_map={"sha_unknown": "sha_xyz"},
            onto="sha_xyz",
            mode="amend",
            user_id="user",
            work_session_id="ws",
        )

        assert "sha_unknown" in result["skipped_shas"]
        assert result["affected_transitions"] == []

    def test_amend_no_user_id_skips_event(self):
        handle = _make_handle()
        _commit(handle, "sha_nouser")

        initial_event_count = len(handle.run_graph.work_events)

        result = handle.adopt_rewrite(
            sha_map={"sha_nouser": "sha_nouser_v2"},
            onto="sha_nouser_v2",
            mode="amend",
        )

        # No new events because user_id=None.
        assert len(handle.run_graph.work_events) == initial_event_count
        assert result["event_id"] is None
        # But payload should still be appended.
        assert len(result["affected_transitions"]) == 1


class TestAdoptRewriteRebase:
    def test_rebase_updates_all_affected_transitions(self):
        handle = _make_handle()
        handle.ensure_work_session(user_id="user", work_session_id="ws")

        t1 = _commit(handle, "old_sha_1")
        t2 = _commit(handle, "old_sha_2")

        result = handle.adopt_rewrite(
            sha_map={"old_sha_1": "new_sha_1", "old_sha_2": "new_sha_2"},
            onto="new_sha_2",
            mode="rebase",
            user_id="user",
            work_session_id="ws",
        )

        assert t1 in result["affected_transitions"]
        assert t2 in result["affected_transitions"]
        assert result["skipped_shas"] == []

    def test_rebase_current_sha_updated(self):
        handle = _make_handle()
        t1 = _commit(handle, "r_old_1")
        t2 = _commit(handle, "r_old_2")

        handle.adopt_rewrite(
            sha_map={"r_old_1": "r_new_1", "r_old_2": "r_new_2"},
            onto="r_new_2",
            mode="rebase",
            user_id="user",
            work_session_id="ws",
        )

        assert handle.run_graph.current_sha(t1) == "r_new_1"
        assert handle.run_graph.current_sha(t2) == "r_new_2"

    def test_rebase_records_rebase_event(self):
        handle = _make_handle()
        t1 = _commit(handle, "sha_x1")
        t2 = _commit(handle, "sha_x2")

        result = handle.adopt_rewrite(
            sha_map={"sha_x1": "sha_y1", "sha_x2": "sha_y2"},
            onto="sha_y2",
            mode="rebase",
            user_id="user",
            work_session_id="ws",
        )

        rebase_events = [
            e for e in handle.run_graph.work_events if e.event_type == REBASE_EVENT
        ]
        assert len(rebase_events) == 1
        evt = rebase_events[0]
        assert evt.data["onto"] == "sha_y2"
        assert set(evt.data["sha_map"].keys()) == {"sha_x1", "sha_x2"}
        assert t1 in evt.data["affected_transitions"]
        assert t2 in evt.data["affected_transitions"]

    def test_rebase_partial_skip(self):
        """sha_map entries with no matching transition go to skipped_shas."""
        handle = _make_handle()
        t1 = _commit(handle, "known_sha")

        result = handle.adopt_rewrite(
            sha_map={"known_sha": "known_new", "orphan_sha": "orphan_new"},
            onto="known_new",
            mode="rebase",
            user_id="user",
            work_session_id="ws",
        )

        assert t1 in result["affected_transitions"]
        assert "orphan_sha" in result["skipped_shas"]

    def test_rebase_branch_inherited_from_existing_payload(self):
        """New GitChangePayload should inherit branch from existing payload."""
        handle = _make_handle()
        t1 = _commit(handle, "inherit_sha", branch="feature/abc")

        handle.adopt_rewrite(
            sha_map={"inherit_sha": "inherit_sha_new"},
            onto="inherit_sha_new",
            mode="rebase",
            user_id="user",
            work_session_id="ws",
        )

        git_payloads = handle.run_graph.payloads_for_transition(
            t1, payload_type="git_change"
        )
        # Both old and new payloads.
        assert len(git_payloads) == 2
        newest = git_payloads[-1]
        assert isinstance(newest, GitChangePayload)
        assert newest.branch == "feature/abc"
        assert newest.head_commit == "inherit_sha_new"
