"""Attach explicit Git commits to a Step."""

from __future__ import annotations

from pathlib import Path

from arctx.core.cuts import is_inactive_step
from arctx.ext.git.helpers import repo as git_repo
from arctx.core.run.handle import RunHandle
from arctx.ext.git.payloads import GitChangePayload


def attach_commits_to_step(
    handle: RunHandle,
    run_dir: Path,
    step_id: str,
    commits: tuple[str, ...],
    *,
    user_id: str = "user",
    lane_id: str | None = None,
) -> dict:
    """Attach explicit Git commits as a GitChangePayload.

    Only the commit hashes and the branch are recorded. Subjects, diff stats,
    and patch text are derived from the repository when something displays the
    payload — see :mod:`arctx.ext.git.derive`.
    """
    if not commits:
        raise ValueError("at least one --commit is required")
    if step_id not in handle.run_graph.steps:
        raise KeyError(f"unknown step_id: {step_id}")
    if is_inactive_step(handle.run_graph, step_id):
        raise ValueError(f"step {step_id} is inactive (cut)")

    repo_root = git_repo.find_repo_root(Path("."))
    resolved_list = []
    for ref in commits:
        try:
            resolved_list.append(git_repo.resolve_commit(repo_root, ref))
        except Exception as exc:  # noqa: BLE001 — any git failure is the same answer
            # A bad ref is user input, not a crash. The CLI catches ValueError
            # and prints one line; a raw CalledProcessError printed a traceback.
            raise ValueError(
                f"not a commit in this repository: {ref!r}"
            ) from exc
    resolved = tuple(resolved_list)
    branch = git_repo.current_branch(repo_root) or ""

    payload_id = handle._next_id("pl")
    gcp = GitChangePayload(
        payload_id=payload_id,
        target_id=step_id,
        branch=branch,
        head_commit=resolved[-1],
        commits=resolved,
        metadata={"attached_by": user_id},
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
        },
        "next": [
            f"arctx git diff --step {step_id}",
        ],
    }
