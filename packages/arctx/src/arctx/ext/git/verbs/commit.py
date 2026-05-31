"""RunHandle.git.commit implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from arctx.core.schema.graph import Transition
from arctx.ext.git.helpers.repo import resolve_worktree_path
from arctx.ext.git.registry import resolve_repo_id
from arctx.ext.git.verbs._forward_transition import (
    capture_git_info,
    check_branch_tip_consistency,
    record_forward_transition,
    resolve_current_branch,
    resolve_current_node_ids,
)


def commit_impl(
    self,
    *,
    message: str,
    branch: str | None = None,
    repo_path: Path | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
    head_commit: str | None = None,
    from_node_ids: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> Transition:
    """Drive a git commit and record the corresponding arctx Transition.

    ``from_node_ids`` explicitly anchors the new transition's input node(s),
    branching the experiment off a chosen node instead of the session/branch
    tip. This is how sibling experiments fan out from a shared baseline.
    """
    resolved_repo_path: Path = resolve_worktree_path(repo_path)

    explicit_from = from_node_ids is not None
    current_node_ids = (
        tuple(from_node_ids)
        if explicit_from
        else resolve_current_node_ids(self, work_session_id)
    )

    for nid in current_node_ids:
        self._ensure_active_node(nid)

    current_branch = resolve_current_branch(
        branch=branch,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    repo_id = "" if dry_run else resolve_repo_id(self, resolved_repo_path)

    # When the caller explicitly branches from a chosen node, that intent
    # overrides the branch-tip fast-forward guard.
    if work_session_id is not None and not explicit_from:
        check_branch_tip_consistency(
            self.run_graph, current_branch, current_node_ids, repo_id
        )

    if not dry_run:
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(resolved_repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                ["git", "commit", "-m", message],
                result.stdout,
                result.stderr,
            )

    if head_commit is None:
        if dry_run:
            head_commit = "dry_run_sha_" + self._next_id("sha")
        else:
            from arctx.ext.git.helpers import repo as git_repo  # noqa: PLC0415
            head_commit = git_repo.current_commit(resolved_repo_path)

    diff_summary, commit_log = capture_git_info(
        head_commit=head_commit,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    return record_forward_transition(
        self,
        current_node_ids=current_node_ids,
        current_branch=current_branch,
        head_commit=head_commit,
        diff_summary=diff_summary,
        commit_log=commit_log,
        extra_payloads=[],
        event_type="commit_created",
        event_summary=message,
        event_data={
            "message": message,
            "branch": current_branch,
            "head_commit": head_commit,
        },
        user_id=user_id,
        work_session_id=work_session_id,
        repo_id=repo_id,
    )
