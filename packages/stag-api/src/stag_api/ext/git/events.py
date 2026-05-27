"""Git-specific WorkEvent helpers.

Branch tip, amend, rebase, and reset events are git-specific and live here.
Session pointer events (generic) remain in stag.core.schema.work_helpers.
"""

from __future__ import annotations

from stag_api.core.schema.work import WorkEvent

# Event type constants.
BRANCH_TIP_EVENT = "branch_tip"
AMEND_EVENT = "amend"
REBASE_EVENT = "rebase"
RESET_EVENT = "reset"


def make_branch_tip_event(
    *,
    event_id: str,
    run_id: str,
    work_session_id: str,
    user_id: str,
    branch: str,
    tip_node_id: str,
) -> WorkEvent:
    """Build a BranchTipEvent as a WorkEvent.

    Records the current tip node for a branch. The latest such event per
    branch is authoritative (``branch_members`` uses this tip for ancestry
    queries).
    """
    return WorkEvent(
        event_id=event_id,
        run_id=run_id,
        work_session_id=work_session_id,
        user_id=user_id,
        event_type=BRANCH_TIP_EVENT,
        data={
            "branch": branch,
            "tip_node_id": tip_node_id,
        },
    )


def make_amend_event(
    *,
    event_id: str,
    run_id: str,
    work_session_id: str,
    user_id: str,
    transition_id: str,
    old_sha: str,
    new_sha: str,
) -> WorkEvent:
    """Build an AmendEvent as a WorkEvent."""
    return WorkEvent(
        event_id=event_id,
        run_id=run_id,
        work_session_id=work_session_id,
        user_id=user_id,
        event_type=AMEND_EVENT,
        data={
            "transition_id": transition_id,
            "old_sha": old_sha,
            "new_sha": new_sha,
        },
    )


def make_rebase_event(
    *,
    event_id: str,
    run_id: str,
    work_session_id: str,
    user_id: str,
    sha_map: dict[str, str],
    affected_transitions: tuple[str, ...],
    onto: str,
) -> WorkEvent:
    """Build a RebaseEvent as a WorkEvent."""
    return WorkEvent(
        event_id=event_id,
        run_id=run_id,
        work_session_id=work_session_id,
        user_id=user_id,
        event_type=REBASE_EVENT,
        data={
            "sha_map": dict(sha_map),
            "affected_transitions": list(affected_transitions),
            "onto": onto,
        },
    )


def make_reset_event(
    *,
    event_id: str,
    run_id: str,
    work_session_id: str,
    user_id: str,
    from_node_id: str,
    to_node_id: str,
    mode: str,
    discarded_transition_ids: tuple[str, ...],
) -> WorkEvent:
    """Build a ResetEvent as a WorkEvent."""
    return WorkEvent(
        event_id=event_id,
        run_id=run_id,
        work_session_id=work_session_id,
        user_id=user_id,
        event_type=RESET_EVENT,
        data={
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "mode": mode,
            "discarded_transition_ids": list(discarded_transition_ids),
        },
    )


def latest_branch_tip(graph, branch: str) -> WorkEvent | None:
    """Return the latest BranchTipEvent for the given branch."""
    result: WorkEvent | None = None
    for event in graph.work_events:
        if (
            event.event_type == BRANCH_TIP_EVENT
            and event.data.get("branch") == branch
        ):
            result = event
    return result
