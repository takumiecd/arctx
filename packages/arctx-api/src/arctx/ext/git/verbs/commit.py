"""RunHandle.git.commit implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from arctx.core.schema.graph import Transition
from arctx.ext.git.helpers.repo import resolve_worktree_path
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
    dry_run: bool = False,
) -> Transition:
    """Drive a git commit and record the corresponding arctx Transition."""
    resolved_repo_path: Path = resolve_worktree_path(repo_path)

    current_node_ids = resolve_current_node_ids(self, work_session_id)

    for nid in current_node_ids:
        self._ensure_active_node(nid)

    current_branch = resolve_current_branch(
        branch=branch,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    if work_session_id is not None:
        check_branch_tip_consistency(self.run_graph, current_branch, current_node_ids)

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
    )
