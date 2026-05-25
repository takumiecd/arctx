"""stag git finish implementation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from stag.core.cuts import is_inactive_transition
from stag.core.git import repo as git_repo
from stag.core.git.session import (
    GitSession,
    clear_current_pointer,
    load_session,
    save_session,
)
from stag.core.schema.payloads import (
    CommitEntry,
    DiffSummary,
    GitChangePayload,
    PredictionPayload,
    ResultPayload,
)
from stag.core.run.handle import RunHandle

_RESULT_FORM_B_OPTIONS = (
    "--status",
    "--summary",
    "--artifact",
    "--raw-output",
    "--log",
    "--metric",
    "--error",
)


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
    # Return relative path from run_dir
    return str(target.relative_to(run_dir))


def _collect_git_data(session: GitSession, repo_root: Path) -> dict:
    """Read all git data needed to build a GitChangePayload."""
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
    """Run validation checks 1-5 common to both forms.  Returns warnings list."""
    errors: list[str] = []

    # 2. session belongs to current run
    if session.run_id != handle.run_id:
        raise ValueError(
            f"session {session.session_id} belongs to run {session.run_id!r}, "
            f"not current run {handle.run_id!r}"
        )
    # 3. session is open
    if not session.is_open:
        raise ValueError(
            f"session {session.session_id} is already closed (closed_at={session.closed_at})"
        )
    if session.transition_id not in handle.run_graph.transitions:
        raise KeyError(f"session references unknown transition_id: {session.transition_id}")
    if is_inactive_transition(handle.run_graph, session.transition_id):
        raise ValueError(f"transition {session.transition_id} is inactive (cut)")
    return []


def git_finish_form_a(
    handle: RunHandle,
    run_dir: Path,
    session_id: str,
    *,
    status: str = "completed",
    summary: str | None = None,
    artifacts: tuple[str, ...] = (),
    raw_outputs: tuple[str, ...] = (),
    logs: tuple[str, ...] = (),
    metrics: dict[str, float] | None = None,
    errors_list: tuple[str, ...] = (),
    matched_prediction_transition_id: str | None = None,
    user_id: str = "user",
    work_session_id: str | None = None,
) -> dict:
    """Create a result node and attach Result/GitChange payloads to the Transition.

    Returns a result dict with created IDs, git info, warnings, and next hints.
    """
    # 1. Load session
    session = load_session(session_id, run_dir)

    # Validation checks 1-5
    _validate_session(session, handle)

    transition_id = session.transition_id

    # 6. matched_prediction validation
    if matched_prediction_transition_id is not None:
        mpid = matched_prediction_transition_id
        if mpid not in handle.run_graph.transitions:
            raise KeyError(f"unknown matched_prediction_transition_id: {mpid}")
        pred_payloads = handle.run_graph.payloads_for_transition(mpid)
        if not any(isinstance(p, PredictionPayload) for p in pred_payloads):
            raise ValueError(
                f"matched_prediction_transition_id does not point to a PredictionPayload: {mpid}"
            )
        if is_inactive_transition(handle.run_graph, mpid):
            raise ValueError(f"matched_prediction_transition_id is inactive: {mpid}")

    # 15. repo root matches
    try:
        current_root = git_repo.find_repo_root(Path("."))
    except Exception as exc:
        raise ValueError("cannot detect git repo root") from exc
    if str(current_root) != session.repo_root:
        raise ValueError(
            f"current repo root {str(current_root)!r} differs from session repo root "
            f"{session.repo_root!r}"
        )

    # 16. branch check
    branch = git_repo.current_branch(current_root)
    if branch is None:
        raise ValueError("HEAD is detached. Cannot finish session.")
    if branch != session.base_branch:
        raise ValueError(
            f"current branch {branch!r} differs from session base branch "
            f"{session.base_branch!r}. Branch switching is not allowed."
        )

    # 17. dirty check (tracked files)
    if git_repo.is_dirty(current_root):
        raise ValueError(
            "Working tree has uncommitted tracked-file changes. "
            "Commit or stash before running 'stag git finish'."
        )

    # 18. detached HEAD already checked via branch == None above

    # Collect warnings
    warnings: list[str] = []

    # Duplicate observation warning
    existing_results = handle.run_graph.payloads_for_transition(
        transition_id, payload_type="result"
    )
    if existing_results:
        warnings.append(
            f"Transition {transition_id} already has {len(existing_results)} ResultPayload(s)."
        )

    # Parallel session warning
    from stag.core.git.session import list_sessions

    for s in list_sessions(run_dir):
        if s.transition_id == transition_id and s.is_open and s.session_id != session_id:
            warnings.append(
                f"Another open GitSession ({s.session_id}) is tracking the same "
                f"Transition {transition_id}."
            )
            break

    # Collect git data (step 1 of atomicity)
    gdata = _collect_git_data(session, current_root)
    head_commit = gdata["head_commit"]

    # Empty diff warning
    if head_commit == session.base_commit or (
        not gdata["changed_files"] and not gdata["commit_log"]
    ):
        warnings.append(
            f"No commits or diff between base_commit {session.base_commit} and HEAD. "
            "An empty GitChangePayload will be attached."
        )

    # Step 2-5: patch artifact
    # Mint payload id for patch naming
    git_payload_id_tentative = handle._next_id("pl")

    patch_artifact: str | None = None
    if gdata["patch_text"]:
        patch_artifact = _write_patch_artifact(
            gdata["patch_text"], git_payload_id_tentative, run_dir
        )

    # Step 6: graph transaction
    # Build ResultPayload template
    meta: dict = {}
    if summary is not None:
        meta["summary"] = summary

    result_template = ResultPayload(
        payload_id="pending",
        target_id="pending",
        status=status,  # type: ignore[arg-type]
        artifacts=artifacts,
        raw_outputs=raw_outputs,
        logs=logs,
        metrics=dict(metrics or {}),
        errors=errors_list,
        matched_prediction_transition_id=matched_prediction_transition_id,
        metadata=meta,
    )
    result_node = handle.observe(
        transition_id,
        result_template,
        user_id=user_id,
        work_session_id=work_session_id,
    )
    result_pl_id = handle.run_graph.payloads_by_transition[transition_id][-1]

    gcp = GitChangePayload(
        payload_id=git_payload_id_tentative,
        target_id=transition_id,
        repo_root=session.repo_root,
        base_commit=session.base_commit,
        head_commit=head_commit,
        branch=branch,
        commits=gdata["commits"],
        commit_log=gdata["commit_log"],
        diff_summary=gdata["diff_summary"],
        changed_files=gdata["changed_files"],
        patch_artifact=patch_artifact,
    )
    handle.run_graph.attach_payload(gcp)
    handle.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="git_change_attached",
        target_kind="transition",
        target_id=transition_id,
        created_records=(git_payload_id_tentative,),
        summary=f"{len(gdata['commit_log'])} commit(s)",
        data={"head_commit": head_commit, "branch": branch},
    )

    # Step 7: close session
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    closed_session = GitSession(
        session_id=session.session_id,
        run_id=session.run_id,
        transition_id=session.transition_id,
        repo_root=session.repo_root,
        base_commit=session.base_commit,
        base_branch=session.base_branch,
        base_dirty=session.base_dirty,
        started_at=session.started_at,
        started_by=session.started_by,
        closed_at=now,
        closed_by=user_id,
        result_node_id=result_node.node_id,
        metadata=dict(session.metadata),
    )
    save_session(closed_session, run_dir)

    # Step 8: clear current pointer if it points to this session
    clear_current_pointer(session_id, run_dir)

    return {
        "created": {
            "transition_id": transition_id,
            "result_node_id": result_node.node_id,
            "result_payload_id": result_pl_id,
            "git_change_payload_id": git_payload_id_tentative,
        },
        "linked": {
            "matched_prediction_transition_id": matched_prediction_transition_id,
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
            f"stag trace --from-node {result_node.node_id}",
            f"stag git diff --transition {transition_id}",
        ],
    }


def git_finish_form_b(
    handle: RunHandle,
    run_dir: Path,
    session_id: str,
    *,
    transition_id: str,
    user_id: str = "user",
    work_session_id: str | None = None,
) -> dict:
    """Attach GitChangePayload to an existing result-bearing Transition.

    Returns a result dict with created IDs, git info, warnings, and next hints.
    """
    # 1. Load session
    session = load_session(session_id, run_dir)

    # Validation checks 1-5
    _validate_session(session, handle)

    session_transition_id = session.transition_id

    if transition_id not in handle.run_graph.transitions:
        raise KeyError(f"unknown transition_id: {transition_id}")
    if transition_id != session_transition_id:
        raise ValueError(
            f"transition {transition_id} does not match session transition "
            f"{session_transition_id!r}"
        )

    if is_inactive_transition(handle.run_graph, transition_id):
        raise ValueError(f"transition {transition_id} is inactive (cut)")

    result_payloads = handle.run_graph.payloads_for_transition(transition_id, payload_type="result")
    if not result_payloads:
        raise ValueError(
            f"transition {transition_id} has no ResultPayload. "
            "Attach mode only supports observed result transitions."
        )

    # 15. repo root matches
    try:
        current_root = git_repo.find_repo_root(Path("."))
    except Exception as exc:
        raise ValueError("cannot detect git repo root") from exc
    if str(current_root) != session.repo_root:
        raise ValueError(
            f"current repo root {str(current_root)!r} differs from session repo root "
            f"{session.repo_root!r}"
        )

    # 16. branch check
    branch = git_repo.current_branch(current_root)
    if branch is None:
        raise ValueError("HEAD is detached. Cannot finish session.")
    if branch != session.base_branch:
        raise ValueError(
            f"current branch {branch!r} differs from session base branch "
            f"{session.base_branch!r}. Branch switching is not allowed."
        )

    # 17. dirty check
    if git_repo.is_dirty(current_root):
        raise ValueError(
            "Working tree has uncommitted tracked-file changes. "
            "Commit or stash before running 'stag git finish'."
        )

    # Collect warnings
    warnings: list[str] = []

    # Duplicate GitChangePayload warning
    existing_gcp = handle.run_graph.payloads_for_transition(
        transition_id, payload_type="git_change"
    )
    if existing_gcp:
        warnings.append(
            f"Transition {transition_id} already has "
            f"{len(existing_gcp)} GitChangePayload(s). Attaching another is allowed "
            "but unusual."
        )

    # Parallel session warning
    from stag.core.git.session import list_sessions

    for s in list_sessions(run_dir):
        if s.transition_id == session_transition_id and s.is_open and s.session_id != session_id:
            warnings.append(
                f"Another open GitSession ({s.session_id}) is tracking the same "
                f"Transition {session_transition_id}."
            )
            break

    # Collect git data
    gdata = _collect_git_data(session, current_root)
    head_commit = gdata["head_commit"]

    # Empty diff warning
    if head_commit == session.base_commit or (
        not gdata["changed_files"] and not gdata["commit_log"]
    ):
        warnings.append(
            f"No commits or diff between base_commit {session.base_commit} and HEAD. "
            "An empty GitChangePayload will be attached."
        )

    # Mint payload id
    git_payload_id = handle._next_id("pl")

    patch_artifact: str | None = None
    if gdata["patch_text"]:
        patch_artifact = _write_patch_artifact(gdata["patch_text"], git_payload_id, run_dir)

    # Attach GitChangePayload
    gcp = GitChangePayload(
        payload_id=git_payload_id,
        target_id=transition_id,
        repo_root=session.repo_root,
        base_commit=session.base_commit,
        head_commit=head_commit,
        branch=branch,
        commits=gdata["commits"],
        commit_log=gdata["commit_log"],
        diff_summary=gdata["diff_summary"],
        changed_files=gdata["changed_files"],
        patch_artifact=patch_artifact,
    )
    handle.run_graph.attach_payload(gcp)
    handle.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="git_change_attached",
        target_kind="transition",
        target_id=transition_id,
        created_records=(git_payload_id,),
        summary=f"{len(gdata['commit_log'])} commit(s)",
        data={"head_commit": head_commit, "branch": branch},
    )

    # Close session
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    closed_session = GitSession(
        session_id=session.session_id,
        run_id=session.run_id,
        transition_id=session.transition_id,
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

    # Clear current pointer if applicable
    clear_current_pointer(session_id, run_dir)

    return {
        "created": {
            "transition_id": transition_id,
            "result_payload_id": None,
            "git_change_payload_id": git_payload_id,
        },
        "linked": {
            "matched_prediction_transition_id": None,
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
            f"stag git diff --transition {transition_id}",
        ],
    }
