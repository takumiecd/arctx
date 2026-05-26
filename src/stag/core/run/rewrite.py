"""RunHandle.adopt_rewrite implementation.

Handles amend and rebase operations by appending new GitChangePayloads to
existing transitions whose current sha matches the old sha in the sha_map.

S4 scope: pick / reword (sha-only updates) only.
drop / squash / fixup are TODO for S5 (interactive rebase full support).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from stag.core.schema.payloads import DiffSummary, GitChangePayload
from stag.core.schema.work_helpers import (
    AMEND_EVENT,
    REBASE_EVENT,
    make_amend_event,
    make_rebase_event,
)

if TYPE_CHECKING:
    from stag.core.schema.payloads import CommitEntry


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
    """Append new GitChangePayload(s) to transitions whose latest sha is in sha_map.

    For each (old_sha, new_sha) in sha_map:
    - Find the transition t with current_sha == old_sha.
    - If not found: skip and record in skipped_shas.
    - Else: build a new GitChangePayload(target=t, branch, head_commit=new_sha,
      diff_summary, commit_log) and attach it.

    Then record one AmendEvent (mode="amend") or RebaseEvent (mode="rebase").

    Parameters
    ----------
    sha_map:
        Mapping of old_sha -> new_sha for each rewritten commit.
    onto:
        The rebase target commit (or new_sha for amend).
    mode:
        "amend" for a single-commit amend; "rebase" for a rebase.
    branch:
        Override branch name for new GitChangePayloads.
        If None, branch is copied from the existing GitChangePayload.
    user_id:
        User ID for work events.
    work_session_id:
        Work session ID for work events.
    diff_summaries:
        Optional per-new_sha DiffSummary. If absent, DiffSummary(0, 0, 0) is used.
    commit_logs:
        Optional per-new_sha commit log. If absent, empty tuple is used.

    Returns
    -------
    dict with keys:
        - affected_transitions: list of transition IDs that got new GitChangePayloads
        - skipped_shas: list of old shas where no matching transition was found
        - event_id: ID of the recorded AmendEvent or RebaseEvent (None if no
          work_session_id / user_id provided)

    Notes
    -----
    TODO (S5): Handle interactive rebase drop (CutPayload) and squash/fixup
    (SquashedIntoPayload + CutPayload on absorbed side, new GitChangePayload on
    survivor). This implementation treats all entries as pick-equivalent (sha update
    only).
    """
    affected_transitions: list[str] = []
    skipped_shas: list[str] = []

    _diff_summaries = diff_summaries or {}
    _commit_logs = commit_logs or {}

    for old_sha, new_sha in sha_map.items():
        t_id = self.run_graph.transition_by_sha(old_sha)
        if t_id is None:
            skipped_shas.append(old_sha)
            continue

        # Resolve branch: prefer caller-supplied, else copy from existing payload.
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

    # Record one AmendEvent or RebaseEvent.
    event_id: str | None = None
    if user_id is not None and work_session_id is not None:
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)
        eid = self._next_id("we")

        if mode == AMEND_EVENT or mode == "amend":
            # For amend, sha_map should have exactly 1 entry.
            items = list(sha_map.items())
            if items:
                old_sha_single, new_sha_single = items[0]
            else:
                old_sha_single, new_sha_single = ("", onto)
            # Find affected transition (may be in skipped if not found).
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
