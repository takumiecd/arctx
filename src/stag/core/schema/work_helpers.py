"""Helper constructors and query functions for WorkEvent subtypes.

SessionPointerEvent and BranchTipEvent are represented as generic WorkEvent
records with a distinguished event_type string, not as separate dataclasses.
"""

from __future__ import annotations

from stag.core.schema.work import WorkEvent

# Event type constants.
SESSION_POINTER_EVENT = "session_pointer"
BRANCH_TIP_EVENT = "branch_tip"


def make_session_pointer_event(
    *,
    event_id: str,
    run_id: str,
    work_session_id: str,
    user_id: str,
    current_node_ids: tuple[str, ...],
    current_branch: str | None,
) -> WorkEvent:
    """Build a SessionPointerEvent as a WorkEvent.

    Records the current node set and branch for a work session.
    The latest such event per session is authoritative ("current" position).

    Parameters
    ----------
    event_id:
        Unique event identifier.
    run_id:
        Run this event belongs to.
    work_session_id:
        Session whose pointer is being updated.
    user_id:
        User performing the update.
    current_node_ids:
        The new current node set for this session (usually 1 element).
    current_branch:
        The git branch active for this session, or None.
    """
    return WorkEvent(
        event_id=event_id,
        run_id=run_id,
        work_session_id=work_session_id,
        user_id=user_id,
        event_type=SESSION_POINTER_EVENT,
        data={
            "current_node_ids": list(current_node_ids),
            "current_branch": current_branch,
        },
    )


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

    Parameters
    ----------
    event_id:
        Unique event identifier.
    run_id:
        Run this event belongs to.
    work_session_id:
        Session that advanced the tip.
    user_id:
        User performing the update.
    branch:
        Git branch name.
    tip_node_id:
        The node ID of the new branch tip.
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


def latest_session_pointer(graph, work_session_id: str) -> WorkEvent | None:
    """Return the latest SessionPointerEvent for the given session.

    Parameters
    ----------
    graph:
        A ``RunGraph`` instance.
    work_session_id:
        Session to query.

    Returns
    -------
    The most recent WorkEvent with event_type="session_pointer" for the
    session, or None if no such event exists.
    """
    result: WorkEvent | None = None
    for event in graph.work_events:
        if (
            event.event_type == SESSION_POINTER_EVENT
            and event.work_session_id == work_session_id
        ):
            result = event
    return result


def latest_branch_tip(graph, branch: str) -> WorkEvent | None:
    """Return the latest BranchTipEvent for the given branch.

    Parameters
    ----------
    graph:
        A ``RunGraph`` instance.
    branch:
        Git branch name to query.

    Returns
    -------
    The most recent WorkEvent with event_type="branch_tip" for *branch*,
    or None if no such event exists.
    """
    result: WorkEvent | None = None
    for event in graph.work_events:
        if (
            event.event_type == BRANCH_TIP_EVENT
            and event.data.get("branch") == branch
        ):
            result = event
    return result
