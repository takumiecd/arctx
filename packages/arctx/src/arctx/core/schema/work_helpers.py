"""Helper constructors and query functions for WorkEvent subtypes.

LanePointerEvent and BranchTipEvent are represented as generic WorkEvent
records with a distinguished event_type string, not as separate dataclasses.
"""

from __future__ import annotations

from arctx.core.schema.work import WorkEvent

# Event type constants.
LANE_POINTER_EVENT = "lane_pointer"
_OLD_SESSION_POINTER_EVENT = "session_pointer"
BRANCH_TIP_EVENT = "branch_tip"
AMEND_EVENT = "amend"
REBASE_EVENT = "rebase"
RESET_EVENT = "reset"


def make_lane_pointer_event(
    *,
    event_id: str,
    run_id: str,
    lane_id: str,
    user_id: str,
    current_node_ids: tuple[str, ...],
    current_branch: str | None,
) -> WorkEvent:
    """Build a LanePointerEvent as a WorkEvent.

    Records the current node set and branch for a lane.
    The latest such event per lane is authoritative ("current" position).

    Parameters
    ----------
    event_id:
        Unique event identifier.
    run_id:
        Run this event belongs to.
    lane_id:
        Lane whose pointer is being updated.
    user_id:
        User performing the update.
    current_node_ids:
        The new current node set for this lane (usually 1 element).
    current_branch:
        The git branch active for this lane, or None.
    """
    return WorkEvent(
        event_id=event_id,
        run_id=run_id,
        lane_id=lane_id,
        user_id=user_id,
        event_type=LANE_POINTER_EVENT,
        data={
            "current_node_ids": list(current_node_ids),
            "current_branch": current_branch,
        },
    )


def make_branch_tip_event(
    *,
    event_id: str,
    run_id: str,
    lane_id: str,
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
    lane_id:
        Lane that advanced the tip.
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
        lane_id=lane_id,
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
    lane_id: str,
    user_id: str,
    step_id: str,
    old_sha: str,
    new_sha: str,
) -> WorkEvent:
    """Build an AmendEvent as a WorkEvent.

    Records an amend operation for audit. The caller is responsible for also
    appending a new GitChangePayload to the affected step.

    Parameters
    ----------
    event_id:
        Unique event identifier.
    run_id:
        Run this event belongs to.
    lane_id:
        Lane in which the amend occurred.
    user_id:
        User performing the amend.
    step_id:
        The arctx step whose sha was amended.
    old_sha:
        The previous HEAD commit SHA (before amend).
    new_sha:
        The new HEAD commit SHA (after amend).
    """
    return WorkEvent(
        event_id=event_id,
        run_id=run_id,
        lane_id=lane_id,
        user_id=user_id,
        event_type=AMEND_EVENT,
        data={
            "step_id": step_id,
            "old_sha": old_sha,
            "new_sha": new_sha,
        },
    )


def make_rebase_event(
    *,
    event_id: str,
    run_id: str,
    lane_id: str,
    user_id: str,
    sha_map: dict[str, str],
    affected_steps: tuple[str, ...],
    onto: str,
) -> WorkEvent:
    """Build a RebaseEvent as a WorkEvent.

    Records a rebase operation for audit (one event per rebase, covering all
    affected steps). The caller is responsible for appending new
    GitChangePayloads to each affected step.

    Parameters
    ----------
    event_id:
        Unique event identifier.
    run_id:
        Run this event belongs to.
    lane_id:
        Lane in which the rebase occurred.
    user_id:
        User performing the rebase.
    sha_map:
        Mapping of old_sha -> new_sha for each rewritten commit.
    affected_steps:
        Step IDs that had new GitChangePayloads appended.
    onto:
        The commit SHA that the branch was rebased onto.
    """
    return WorkEvent(
        event_id=event_id,
        run_id=run_id,
        lane_id=lane_id,
        user_id=user_id,
        event_type=REBASE_EVENT,
        data={
            "sha_map": dict(sha_map),
            "affected_steps": list(affected_steps),
            "onto": onto,
        },
    )


def make_reset_event(
    *,
    event_id: str,
    run_id: str,
    lane_id: str,
    user_id: str,
    from_node_id: str,
    to_node_id: str,
    mode: str,
    discarded_step_ids: tuple[str, ...],
) -> WorkEvent:
    """Build a ResetEvent as a WorkEvent.

    Records a reset operation. Unlike commit/revert/cherry-pick, reset does NOT
    create a new Step. Instead it records the rollback as a WorkEvent and
    updates the lane pointer.

    Parameters
    ----------
    event_id:
        Unique event identifier.
    run_id:
        Run this event belongs to.
    lane_id:
        Lane in which the reset occurred.
    user_id:
        User performing the reset.
    from_node_id:
        The current node ID immediately before the reset.
    to_node_id:
        The target node ID to which HEAD is reset (must be an ancestor of from_node_id).
    mode:
        One of "hard", "mixed", "soft". Only "hard" causes CutPayloads to be
        attached to discarded steps.
    discarded_step_ids:
        Step IDs that are discarded by the reset (output_node_id lies in
        the range between from_node and to_node, exclusive of to_node).
    """
    return WorkEvent(
        event_id=event_id,
        run_id=run_id,
        lane_id=lane_id,
        user_id=user_id,
        event_type=RESET_EVENT,
        data={
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "mode": mode,
            "discarded_step_ids": list(discarded_step_ids),
        },
    )


def latest_lane_pointer(graph, lane_id: str) -> WorkEvent | None:
    """Return the latest LanePointerEvent for the given lane.

    Parameters
    ----------
    graph:
        A ``RunGraph`` instance.
    lane_id:
        Lane to query.

    Returns
    -------
    The most recent lane pointer event for the lane, or None if no such event
    exists. Older runs using event_type="session_pointer" are accepted.
    """
    result: WorkEvent | None = None
    for event in graph.work_events:
        if (
            event.event_type in (LANE_POINTER_EVENT, _OLD_SESSION_POINTER_EVENT)
            and event.lane_id == lane_id
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
