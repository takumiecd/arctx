"""Attach explicit Git commits to a result-bearing Transition."""

from __future__ import annotations

from pathlib import Path

from stag.core.cuts import is_inactive_transition
from stag.core.git import repo as git_repo
from stag.core.git.finish import _write_patch_artifact
from stag.core.run.handle import RunHandle
from stag.core.schema.payloads import CommitEntry, DiffSummary, GitChangePayload


def attach_commits_to_transition(
    handle: RunHandle,
    run_dir: Path,
    transition_id: str,
    commits: tuple[str, ...],
    *,
    user_id: str = "user",
    work_session_id: str | None = None,
) -> dict:
    """Attach explicit Git commits as a GitChangePayload."""
    if not commits:
        raise ValueError("at least one --commit is required")
    if transition_id not in handle.run_graph.transitions:
        raise KeyError(f"unknown transition_id: {transition_id}")
    if is_inactive_transition(handle.run_graph, transition_id):
        raise ValueError(f"transition {transition_id} is inactive (cut)")

    result_payloads = handle.run_graph.payloads_for_transition(transition_id, payload_type="result")
    if not result_payloads:
        raise ValueError(
            f"transition {transition_id} has no ResultPayload. "
            "Git commits can only be attached after an observed result."
        )

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
    changed_files = tuple(git_repo.diff_name_only_for_commits(repo_root, resolved))
    patch_text = git_repo.diff_patch_for_commits(repo_root, resolved)

    payload_id = handle._next_id("pl")
    patch_artifact = None
    if patch_text:
        patch_artifact = _write_patch_artifact(patch_text, payload_id, run_dir)

    gcp = GitChangePayload(
        payload_id=payload_id,
        target_id=transition_id,
        repo_root=str(repo_root),
        base_commit="",
        head_commit=resolved[-1],
        branch=branch,
        commits=resolved,
        commit_log=commit_log,
        diff_summary=diff_summary,
        changed_files=changed_files,
        patch_artifact=patch_artifact,
        metadata={"attached_by": user_id},
    )
    handle.run_graph.attach_payload(gcp)
    handle.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="git_change_attached",
        target_kind="transition",
        target_id=transition_id,
        created_records=(payload_id,),
        summary=f"{len(resolved)} commit(s)",
        data={"commits": list(resolved), "branch": branch},
    )

    return {
        "created": {
            "git_change_payload_id": payload_id,
        },
        "linked": {
            "transition_id": transition_id,
        },
        "git": {
            "commits": list(resolved),
            "branch": branch,
            "files_changed": diff_summary.files_changed,
            "patch_artifact": patch_artifact,
        },
        "next": [
            f"stag git diff --transition {transition_id}",
        ],
    }
