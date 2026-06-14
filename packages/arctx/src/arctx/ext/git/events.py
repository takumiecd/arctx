"""Git-specific WorkEvent helpers.

Branch tip, amend, rebase, and reset events are git-specific and live here.
Session pointer events (generic) remain in arctx.core.schema.work_helpers.
"""

from __future__ import annotations

from arctx.core.schema.work import WorkEvent

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
    repo_id: str = "",
) -> WorkEvent:
    """Build a BranchTipEvent as a WorkEvent.

    Records the current tip node for a branch within a repo. The latest such
    event per ``(repo_id, branch)`` is authoritative (``branch_members`` uses
    this tip for ancestry queries). ``repo_id`` keeps same-named branches in
    different repos (e.g. two ``main``s) from colliding.
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
            "repo_id": repo_id,
        },
    )


def make_amend_event(
    *,
    event_id: str,
    run_id: str,
    work_session_id: str,
    user_id: str,
    step_id: str,
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
            "step_id": step_id,
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
    affected_steps: tuple[str, ...],
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
            "affected_steps": list(affected_steps),
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
    discarded_step_ids: tuple[str, ...],
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
            "discarded_step_ids": list(discarded_step_ids),
        },
    )


def latest_branch_tip(graph, branch: str, repo_id: str | None = None) -> WorkEvent | None:
    """Return the latest BranchTipEvent for the given branch.

    When *repo_id* is given, only events for that repo match, so same-named
    branches in different repos stay distinct. ``repo_id=None`` matches any
    repo (legacy / single-repo callers).
    """
    result: WorkEvent | None = None
    for event in graph.work_events:
        if event.event_type != BRANCH_TIP_EVENT or event.data.get("branch") != branch:
            continue
        if repo_id is not None and event.data.get("repo_id", "") != repo_id:
            continue
        result = event
    return result
