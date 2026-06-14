"""arctx git finish implementation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from arctx.core.cuts import is_inactive_step
from arctx.ext.git.helpers import repo as git_repo
from arctx.ext.git.helpers.session import (
    GitSession,
    clear_current_pointer,
    load_session,
    save_session,
)
from arctx.ext.git.payloads import (
    CommitEntry,
    DiffSummary,
    GitChangePayload,
)
from arctx.core.schema.payloads import StepPayload
from arctx.core.run.handle import RunHandle


def _artifacts_dir(run_dir: Path) -> Path:
    return run_dir / "artifacts" / "git"


def _write_patch_artifact(patch_text: str, payload_id: str, run_dir: Path) -> str:
    """Write *patch_text* atomically and return a relative path string."""
    art_dir = _artifacts_dir(run_dir)
    art_dir.mkdir(parents=True, exist_ok=True)
    target = art_dir / f"{payload_id}.patch"
    fd, tmp = tempfile.mkstemp(dir=art_dir, suffix=".tmp")
    try:
        os.write(fd, patch_text.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return str(target.relative_to(run_dir))


def _collect_git_data(session: GitSession, repo_root: Path) -> dict:
    head_commit = git_repo.current_commit(repo_root)
    raw_log = git_repo.commit_log(repo_root, session.base_commit)
    commit_log = tuple(
        CommitEntry(
            sha=e["sha"],
            subject=e["subject"],
            author=e["author"],
            date=e["date"],
        )
        for e in raw_log
    )
    stat = git_repo.diff_shortstat(repo_root, session.base_commit)
    diff_summary = DiffSummary(
        files_changed=stat["files_changed"],
        insertions=stat["insertions"],
        deletions=stat["deletions"],
    )
    changed_files = tuple(git_repo.diff_name_only(repo_root, session.base_commit))
    patch_text = git_repo.diff_patch(repo_root, session.base_commit)
    return {
        "head_commit": head_commit,
        "commits": tuple(e.sha for e in commit_log),
        "commit_log": commit_log,
        "diff_summary": diff_summary,
        "changed_files": changed_files,
        "patch_text": patch_text,
    }


def _validate_session(session: GitSession, handle: RunHandle) -> list[str]:
    if session.run_id != handle.run_id:
        raise ValueError(
            f"session {session.session_id} belongs to run {session.run_id!r}, "
            f"not current run {handle.run_id!r}"
        )
    if not session.is_open:
        raise ValueError(
            f"session {session.session_id} is already closed (closed_at={session.closed_at})"
        )
    if session.step_id not in handle.run_graph.steps:
        raise KeyError(f"session references unknown step_id: {session.step_id}")
    if is_inactive_step(handle.run_graph, session.step_id):
        raise ValueError(f"step {session.step_id} is inactive (cut)")
    return []


def git_finish_form_a(
    handle: RunHandle,
    run_dir: Path,
    session_id: str,
    *,
    status: str = "completed",
    summary: str | None = None,
    user_id: str = "user",
    work_session_id: str | None = None,
) -> dict:
    """Create a result step and attach GitChangePayload.

    In the new schema, this creates a new Step from the session's
    step output node, with type="result" and attaches a GitChangePayload.
    """
    session = load_session(session_id, run_dir)
    _validate_session(session, handle)
    step_id = session.step_id

    try:
        current_root = git_repo.find_repo_root(Path("."))
    except Exception as exc:
        raise ValueError("cannot detect git repo root") from exc
    if str(current_root) != session.repo_root:
        raise ValueError(
            f"current repo root {str(current_root)!r} differs from session repo root "
            f"{session.repo_root!r}"
        )

    branch = git_repo.current_branch(current_root)
    if branch is None:
        raise ValueError("HEAD is detached. Cannot finish session.")
    if branch != session.base_branch:
        raise ValueError(
            f"current branch {branch!r} differs from session base branch "
            f"{session.base_branch!r}."
        )

    if git_repo.is_dirty(current_root):
        raise ValueError(
            "Working tree has uncommitted tracked-file changes. "
            "Commit or stash before running 'arctx git finish'."
        )

    warnings: list[str] = []

    gdata = _collect_git_data(session, current_root)
    head_commit = gdata["head_commit"]

    if head_commit == session.base_commit or (
        not gdata["changed_files"] and not gdata["commit_log"]
    ):
        warnings.append(
            f"No commits or diff between base_commit {session.base_commit} and HEAD. "
            "An empty GitChangePayload will be attached."
        )

    # The session's step output node is the starting point for the result.
    t = handle.run_graph.steps.get(step_id)
    if t is None:
        raise KeyError(f"unknown step_id: {step_id}")
    from_node_id = t.output_node_id or session.step_id

    # Attach GitChangePayload to the existing step.
    git_payload_id = handle._next_id("pl")
    patch_artifact: str | None = None
    if gdata["patch_text"]:
        patch_artifact = _write_patch_artifact(gdata["patch_text"], git_payload_id, run_dir)

    gcp = GitChangePayload(
        payload_id=git_payload_id,
        target_id=step_id,
        branch=branch,
        head_commit=head_commit,
        diff_summary=gdata["diff_summary"],
        commit_log=gdata["commit_log"],
        metadata={"base_commit": session.base_commit, "patch_artifact": patch_artifact or ""},
    )
    handle.run_graph.attach_payload(gcp)
    handle.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="git_change_attached",
        target_kind="step",
        target_id=step_id,
        created_records=(git_payload_id,),
        summary=f"{len(gdata['commit_log'])} commit(s)",
        data={"head_commit": head_commit, "branch": branch},
    )

    # Close session.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    closed_session = GitSession(
        session_id=session.session_id,
        run_id=session.run_id,
        step_id=session.step_id,
        repo_root=session.repo_root,
        base_commit=session.base_commit,
        base_branch=session.base_branch,
        base_dirty=session.base_dirty,
        started_at=session.started_at,
        started_by=session.started_by,
        closed_at=now,
        closed_by=user_id,
        result_node_id=from_node_id,
        metadata=dict(session.metadata),
    )
    save_session(closed_session, run_dir)
    clear_current_pointer(session_id, run_dir)

    return {
        "created": {
            "step_id": step_id,
            "git_change_payload_id": git_payload_id,
        },
        "git": {
            "base_commit": session.base_commit,
            "head_commit": head_commit,
            "branch": branch,
            "commits": len(gdata["commit_log"]),
            "files_changed": gdata["diff_summary"].files_changed,
            "patch_artifact": patch_artifact,
        },
        "warnings": warnings,
        "next": [
            f"arctx git diff --step {step_id}",
        ],
    }


def git_finish_form_b(
    handle: RunHandle,
    run_dir: Path,
    session_id: str,
    *,
    step_id: str,
    user_id: str = "user",
    work_session_id: str | None = None,
) -> dict:
    """Attach GitChangePayload to an existing Step."""
    session = load_session(session_id, run_dir)
    _validate_session(session, handle)

    if step_id not in handle.run_graph.steps:
        raise KeyError(f"unknown step_id: {step_id}")
    if step_id != session.step_id:
        raise ValueError(
            f"step {step_id} does not match session step "
            f"{session.step_id!r}"
        )
    if is_inactive_step(handle.run_graph, step_id):
        raise ValueError(f"step {step_id} is inactive (cut)")

    try:
        current_root = git_repo.find_repo_root(Path("."))
    except Exception as exc:
        raise ValueError("cannot detect git repo root") from exc
    if str(current_root) != session.repo_root:
        raise ValueError(
            f"current repo root {str(current_root)!r} differs from session repo root "
            f"{session.repo_root!r}"
        )

    branch = git_repo.current_branch(current_root)
    if branch is None:
        raise ValueError("HEAD is detached.")
    if branch != session.base_branch:
        raise ValueError(
            f"current branch {branch!r} differs from session base branch "
            f"{session.base_branch!r}."
        )

    if git_repo.is_dirty(current_root):
        raise ValueError("Working tree has uncommitted tracked-file changes.")

    warnings: list[str] = []
    existing_gcp = handle.run_graph.payloads_for_step(step_id, payload_type="git_change")
    if existing_gcp:
        warnings.append(
            f"Step {step_id} already has "
            f"{len(existing_gcp)} GitChangePayload(s)."
        )

    gdata = _collect_git_data(session, current_root)
    head_commit = gdata["head_commit"]

    if head_commit == session.base_commit or (
        not gdata["changed_files"] and not gdata["commit_log"]
    ):
        warnings.append(
            f"No commits or diff between base_commit {session.base_commit} and HEAD."
        )

    git_payload_id = handle._next_id("pl")
    patch_artifact: str | None = None
    if gdata["patch_text"]:
        patch_artifact = _write_patch_artifact(gdata["patch_text"], git_payload_id, run_dir)

    gcp = GitChangePayload(
        payload_id=git_payload_id,
        target_id=step_id,
        branch=branch,
        head_commit=head_commit,
        diff_summary=gdata["diff_summary"],
        commit_log=gdata["commit_log"],
        metadata={"base_commit": session.base_commit, "patch_artifact": patch_artifact or ""},
    )
    handle.run_graph.attach_payload(gcp)
    handle.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="git_change_attached",
        target_kind="step",
        target_id=step_id,
        created_records=(git_payload_id,),
        summary=f"{len(gdata['commit_log'])} commit(s)",
        data={"head_commit": head_commit, "branch": branch},
    )

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    closed_session = GitSession(
        session_id=session.session_id,
        run_id=session.run_id,
        step_id=session.step_id,
        repo_root=session.repo_root,
        base_commit=session.base_commit,
        base_branch=session.base_branch,
        base_dirty=session.base_dirty,
        started_at=session.started_at,
        started_by=session.started_by,
        closed_at=now,
        closed_by=user_id,
        result_node_id=session.result_node_id,
        metadata=dict(session.metadata),
    )
    save_session(closed_session, run_dir)
    clear_current_pointer(session_id, run_dir)

    return {
        "created": {
            "step_id": step_id,
            "git_change_payload_id": git_payload_id,
        },
        "git": {
            "base_commit": session.base_commit,
            "head_commit": head_commit,
            "branch": branch,
            "commits": len(gdata["commit_log"]),
            "files_changed": gdata["diff_summary"].files_changed,
            "patch_artifact": patch_artifact,
        },
        "warnings": warnings,
        "next": [
            f"arctx git diff --step {step_id}",
        ],
    }
