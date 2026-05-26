"""Internal helper for recording a forward stag Transition with git metadata.

Used by commit_impl, revert_impl, and cherry_pick_impl.  Not part of the
public RunHandle API.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from stag.core.schema.graph import Node, Transition
from stag.core.schema.payloads import (
    BranchPayload,
    CommitEntry,
    DiffSummary,
    GitChangePayload,
    PayloadBase,
)
from stag.core.schema.work_helpers import (
    latest_branch_tip,
    latest_session_pointer,
    make_branch_tip_event,
    make_session_pointer_event,
)

if TYPE_CHECKING:
    from stag.core.run.handle import RunHandle
    from stag.core.run_graph import RunGraph


class ParallelSessionConflict(RuntimeError):
    """Raised when a session tries to commit but another session moved the branch tip."""

    def __init__(self, branch: str, expected_tip: str, current: tuple[str, ...]):
        self.branch = branch
        self.expected_tip = expected_tip
        self.current = current
        super().__init__(
            f"non-fast-forward: branch {branch!r} tip is {expected_tip!r} "
            f"but session current is {list(current)!r}. "
            f"Pull or rebase before committing (stag pull is planned)."
        )


def check_branch_tip_consistency(
    graph: "RunGraph",
    branch: str,
    current_node_ids: tuple[str, ...],
) -> None:
    """Raise ParallelSessionConflict if branch's latest tip is not in current_node_ids.

    If no BranchTipEvent exists for ``branch`` yet (first commit on this branch),
    skip the check (no conflict possible).

    Parameters
    ----------
    graph:
        The RunGraph to query.
    branch:
        The git branch name being committed to.
    current_node_ids:
        The session's current node IDs at commit time.

    Raises
    ------
    ParallelSessionConflict
        If the branch tip exists and is NOT in current_node_ids, indicating
        another session has already advanced the branch.
    """
    tip_event = latest_branch_tip(graph, branch)
    if tip_event is None:
        # No BranchTipEvent yet — first commit on this branch, no conflict possible.
        return

    tip_node_id = tip_event.data.get("tip_node_id")
    if tip_node_id is None:
        # Malformed event — skip the check rather than blocking legitimate commits.
        return

    tip_node_id_str = str(tip_node_id)
    if tip_node_id_str not in current_node_ids:
        raise ParallelSessionConflict(
            branch=branch,
            expected_tip=tip_node_id_str,
            current=current_node_ids,
        )


def resolve_current_node_ids(
    self: "RunHandle",
    work_session_id: str | None,
) -> tuple[str, ...]:
    """Return the current node IDs for a session, or (root,) if none."""
    if work_session_id is not None:
        sp_event = latest_session_pointer(self.run_graph, work_session_id)
        if sp_event is not None:
            raw = sp_event.data.get("current_node_ids") or []
            return tuple(str(n) for n in raw)
    return (self.root_node_id,)


def resolve_current_branch(
    *,
    branch: str | None,
    dry_run: bool,
    repo_path: Path,
) -> str:
    """Resolve the current git branch, falling back to 'unknown'."""
    if branch is not None:
        return branch
    if not dry_run:
        from stag.core.git import repo as git_repo  # noqa: PLC0415
        resolved = git_repo.current_branch(repo_path)
        if resolved is not None:
            return resolved
    return "unknown"


def capture_git_info(
    *,
    head_commit: str,
    dry_run: bool,
    repo_path: Path,
) -> tuple[DiffSummary, tuple[CommitEntry, ...]]:
    """Return (diff_summary, commit_log) for *head_commit* after a git operation."""
    if dry_run:
        return DiffSummary(files_changed=0, insertions=0, deletions=0), ()

    import re  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    diff_summary = DiffSummary(files_changed=0, insertions=0, deletions=0)
    commit_log: tuple[CommitEntry, ...] = ()

    try:
        from stag.core.git import repo as git_repo  # noqa: PLC0415
        raw_log = git_repo.commit_log_for_commits(repo_path, [head_commit])
        commit_log = tuple(
            CommitEntry(
                sha=e["sha"],
                subject=e["subject"],
                author=e["author"],
                date=e["date"],
            )
            for e in raw_log
        )
    except Exception:  # noqa: BLE001
        pass

    try:
        stat_result = subprocess.run(
            ["git", "diff", "--shortstat", "HEAD~1", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if stat_result.returncode == 0 and stat_result.stdout.strip():
            raw = stat_result.stdout.strip()
            fc = re.search(r"(\d+) files? changed", raw)
            ins = re.search(r"(\d+) insertion", raw)
            dls = re.search(r"(\d+) deletion", raw)
            diff_summary = DiffSummary(
                files_changed=int(fc.group(1)) if fc else 0,
                insertions=int(ins.group(1)) if ins else 0,
                deletions=int(dls.group(1)) if dls else 0,
            )
    except Exception:  # noqa: BLE001
        pass

    return diff_summary, commit_log


def record_forward_transition(
    self: "RunHandle",
    *,
    current_node_ids: tuple[str, ...],
    current_branch: str,
    head_commit: str,
    diff_summary: DiffSummary,
    commit_log: tuple[CommitEntry, ...],
    extra_payloads: list[PayloadBase],
    event_type: str,
    event_summary: str,
    event_data: dict,
    user_id: str | None,
    work_session_id: str | None,
) -> Transition:
    """Append node, transition, standard payloads + extra payloads, and work events.

    Parameters
    ----------
    current_node_ids:
        Input node IDs for the new Transition.
    current_branch:
        Git branch name at commit time.
    head_commit:
        New HEAD commit SHA.
    diff_summary:
        Diff stats.
    commit_log:
        Commit log entries.
    extra_payloads:
        Additional payloads to attach (e.g. RevertPayload, CherryPickPayload).
        These must have ``target_id`` set to an empty string; it will be
        replaced with the new transition_id before attaching.
    event_type:
        Work event type string (e.g. "commit_created", "revert_created").
    event_summary:
        Short string for the work event summary field.
    event_data:
        Extra data dict for the work event.
    user_id:
        User ID for attribution. If None, work events are not recorded.
    work_session_id:
        Work session ID. If None, work events are not recorded.

    Returns
    -------
    The newly created Transition.
    """
    # Ensure work session exists.
    if user_id is not None and work_session_id is not None:
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)

    # New Node.
    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    # New Transition.
    transition_id = self._next_id("t")
    transition = Transition(
        transition_id=transition_id,
        input_node_ids=current_node_ids,
        output_node_id=output_node.node_id,
    )
    self.run_graph.add_transition(transition)

    # BranchPayload.
    branch_payload = BranchPayload(
        payload_id=self._next_id("pl"),
        target_id=transition_id,
        branch=current_branch,
    )
    self.run_graph.attach_payload(branch_payload)

    # GitChangePayload.
    git_payload = GitChangePayload(
        payload_id=self._next_id("pl"),
        target_id=transition_id,
        branch=current_branch,
        head_commit=head_commit,
        diff_summary=diff_summary,
        commit_log=commit_log,
    )
    self.run_graph.attach_payload(git_payload)

    # Extra typed payloads (RevertPayload, CherryPickPayload, etc.).
    # Callers must pass them with correct target_id already set.
    for pl in extra_payloads:
        self.run_graph.attach_payload(pl)

    # BranchTipEvent + SessionPointerEvent.
    if user_id is not None and work_session_id is not None:
        tip_event = make_branch_tip_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            branch=current_branch,
            tip_node_id=output_node.node_id,
        )
        self.run_graph.add_work_event(tip_event)

        sp_event = make_session_pointer_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            current_node_ids=(output_node.node_id,),
            current_branch=current_branch,
        )
        self.run_graph.add_work_event(sp_event)

    # Audit work event.
    created = (
        output_node.node_id,
        transition_id,
        branch_payload.payload_id,
        git_payload.payload_id,
        *[pl.payload_id for pl in extra_payloads],
    )
    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type=event_type,
        target_kind="transition",
        target_id=transition_id,
        created_records=created,
        summary=event_summary,
        data=event_data,
    )

    return transition
