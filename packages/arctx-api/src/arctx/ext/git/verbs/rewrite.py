"""RunHandle.git.adopt_rewrite implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from arctx.ext.git.events import (
    AMEND_EVENT,
    make_amend_event,
    make_rebase_event,
)
from arctx.ext.git.payloads import DiffSummary, GitChangePayload
from arctx.ext.git.queries import transition_by_sha

if TYPE_CHECKING:
    from arctx.ext.git.payloads import CommitEntry


def adopt_rewrite_impl(
    self,
    *,
    sha_map: dict[str, str],
    onto: str,
    mode: Literal["amend", "rebase"],
    branch: str | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
    diff_summaries: dict[str, DiffSummary] | None = None,
    commit_logs: dict[str, tuple[CommitEntry, ...]] | None = None,
) -> dict:
    """Append new GitChangePayload(s) to transitions whose latest sha is in sha_map."""
    affected_transitions: list[str] = []
    skipped_shas: list[str] = []

    _diff_summaries = diff_summaries or {}
    _commit_logs = commit_logs or {}

    for old_sha, new_sha in sha_map.items():
        t_id = transition_by_sha(self.run_graph, old_sha)
        if t_id is None:
            skipped_shas.append(old_sha)
            continue

        resolved_branch = branch
        if resolved_branch is None:
            existing_git = self.run_graph.payloads_for_transition(
                t_id, payload_type="git_change"
            )
            if existing_git:
                last_git = existing_git[-1]
                resolved_branch = getattr(last_git, "branch", None)
        if resolved_branch is None:
            resolved_branch = "unknown"

        new_payload = GitChangePayload(
            payload_id=self._next_id("pl"),
            target_id=t_id,
            branch=resolved_branch,
            head_commit=new_sha,
            diff_summary=_diff_summaries.get(new_sha, DiffSummary(0, 0, 0)),
            commit_log=_commit_logs.get(new_sha, ()),
        )
        self.run_graph.attach_payload(new_payload)
        affected_transitions.append(t_id)

    event_id: str | None = None
    if user_id is not None and work_session_id is not None:
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)
        eid = self._next_id("we")

        if mode == AMEND_EVENT or mode == "amend":
            items = list(sha_map.items())
            if items:
                old_sha_single, new_sha_single = items[0]
            else:
                old_sha_single, new_sha_single = ("", onto)
            t_for_amend = affected_transitions[0] if affected_transitions else ""
            event = make_amend_event(
                event_id=eid,
                run_id=self.run_id,
                work_session_id=work_session_id,
                user_id=user_id,
                transition_id=t_for_amend,
                old_sha=old_sha_single,
                new_sha=new_sha_single,
            )
        else:
            event = make_rebase_event(
                event_id=eid,
                run_id=self.run_id,
                work_session_id=work_session_id,
                user_id=user_id,
                sha_map=sha_map,
                affected_transitions=tuple(affected_transitions),
                onto=onto,
            )

        self.run_graph.add_work_event(event)
        event_id = eid

    return {
        "affected_transitions": affected_transitions,
        "skipped_shas": skipped_shas,
        "event_id": event_id,
    }
