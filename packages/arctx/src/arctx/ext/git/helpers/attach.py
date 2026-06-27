"""Attach explicit Git commits to a Step."""

from __future__ import annotations

from pathlib import Path

from arctx.core.cuts import is_inactive_step
from arctx.ext.git.helpers import repo as git_repo
from arctx.ext.git.helpers.finish import _write_patch_artifact
from arctx.core.run.handle import RunHandle
from arctx.ext.git.payloads import CommitEntry, DiffSummary, GitChangePayload


def attach_commits_to_step(
    handle: RunHandle,
    run_dir: Path,
    step_id: str,
    commits: tuple[str, ...],
    *,
    user_id: str = "user",
    lane_id: str | None = None,
) -> dict:
    """Attach explicit Git commits as a GitChangePayload."""
    if not commits:
        raise ValueError("at least one --commit is required")
    if step_id not in handle.run_graph.steps:
        raise KeyError(f"unknown step_id: {step_id}")
    if is_inactive_step(handle.run_graph, step_id):
        raise ValueError(f"step {step_id} is inactive (cut)")

    repo_root = git_repo.find_repo_root(Path("."))
    resolved = tuple(git_repo.resolve_commit(repo_root, c) for c in commits)
    branch = git_repo.current_branch(repo_root) or ""
    commit_log = tuple(
        CommitEntry(
            sha=e["sha"],
            subject=e["subject"],
            author=e["author"],
            date=e["date"],
        )
        for e in git_repo.commit_log_for_commits(repo_root, resolved)
    )
    stat = git_repo.diff_shortstat_for_commits(repo_root, resolved)
    diff_summary = DiffSummary(
        files_changed=stat["files_changed"],
        insertions=stat["insertions"],
        deletions=stat["deletions"],
    )
    patch_text = git_repo.diff_patch_for_commits(repo_root, resolved)

    payload_id = handle._next_id("pl")
    patch_artifact = None
    if patch_text:
        patch_artifact = _write_patch_artifact(patch_text, payload_id, run_dir)

    gcp = GitChangePayload(
        payload_id=payload_id,
        target_id=step_id,
        branch=branch,
        head_commit=resolved[-1],
        diff_summary=diff_summary,
        commit_log=commit_log,
        metadata={"attached_by": user_id, "patch_artifact": patch_artifact or ""},
    )
    handle.run_graph.attach_payload(gcp)
    handle.record_work_event(
        user_id=user_id,
        lane_id=lane_id,
        event_type="git_change_attached",
        target_kind="step",
        target_id=step_id,
        created_records=(payload_id,),
        summary=f"{len(resolved)} commit(s)",
        data={"commits": list(resolved), "branch": branch},
    )

    return {
        "created": {
            "git_change_payload_id": payload_id,
        },
        "linked": {
            "step_id": step_id,
        },
        "git": {
            "commits": list(resolved),
            "branch": branch,
            "files_changed": diff_summary.files_changed,
            "patch_artifact": patch_artifact,
        },
        "next": [
            f"arctx git diff --step {step_id}",
        ],
    }
