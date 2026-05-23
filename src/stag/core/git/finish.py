"""stag git finish implementation (form A and form B).

Form A: create new OutputTransition + ResultPayload + GitChangePayload.
Form B: attach GitChangePayload to an existing observed OutputTransition.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from stag.core.cuts import is_inactive_input_transition, is_inactive_output_transition
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
    # 4. IT exists
    if session.input_transition_id not in handle.run_graph.input_transitions:
        raise KeyError(
            f"session references unknown input_transition_id: {session.input_transition_id}"
        )
    # 5. IT is active
    if is_inactive_input_transition(handle.run_graph, session.input_transition_id):
        raise ValueError(
            f"input_transition {session.input_transition_id} is inactive (cut)"
        )
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
    matched_prediction_output_id: str | None = None,
    user_id: str = "user",
) -> dict:
    """Form A: create new OT + ResultPayload + GitChangePayload.

    Returns a result dict with created IDs, git info, warnings, and next hints.
    """
    # 1. Load session
    session = load_session(session_id, run_dir)

    # Validation checks 1-5
    _validate_session(session, handle)

    it_id = session.input_transition_id

    # 6. matched_prediction validation
    if matched_prediction_output_id is not None:
        mpid = matched_prediction_output_id
        if mpid not in handle.run_graph.output_transitions:
            raise KeyError(f"unknown matched_prediction_output_id: {mpid}")
        pred_payloads = handle.run_graph.payloads_for_output_transition(mpid)
        if not any(isinstance(p, PredictionPayload) for p in pred_payloads):
            raise ValueError(
                f"matched_prediction_output_id does not point to a PredictionPayload: {mpid}"
            )
        matched_ot = handle.run_graph.output_transitions[mpid]
        if matched_ot.input_transition_id != it_id:
            raise ValueError(
                f"matched_prediction_output_id {mpid} belongs to a different "
                f"input_transition than session: {matched_ot.input_transition_id!r} != {it_id!r}"
            )
        if is_inactive_output_transition(handle.run_graph, mpid):
            raise ValueError(f"matched_prediction_output_id is inactive: {mpid}")

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
    existing_result_ots = handle.run_graph.output_ids_for_input(it_id, kind="result")
    if existing_result_ots:
        warnings.append(
            f"InputTransition {it_id} already has observed OutputTransition(s): "
            f"{existing_result_ots}. Consider using "
            f"'stag git finish {session_id} --output-transition <ot_id>' instead."
        )

    # Parallel session warning
    from stag.core.git.session import list_sessions
    for s in list_sessions(run_dir):
        if (
            s.input_transition_id == it_id
            and s.is_open
            and s.session_id != session_id
        ):
            warnings.append(
                f"Another open GitSession ({s.session_id}) is tracking the same "
                f"InputTransition {it_id}."
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
    pl_count = handle._counters.get("pl", 0) + 1
    handle._counters["pl"] = pl_count
    from stag.core.ids import sequential_id
    git_payload_id_tentative = sequential_id("pl", pl_count)

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
        matched_prediction_output_id=matched_prediction_output_id,
        metadata=meta,
    )
    # observe() will mint new node + OT + ResultPayload internally
    ot = handle.observe(it_id, result_template, user_id=user_id)
    result_pl_id = handle.run_graph.payloads_by_output_transition[ot.output_transition_id][-1]

    # Now attach GitChangePayload with the pre-minted id
    gcp = GitChangePayload(
        payload_id=git_payload_id_tentative,
        target_id=ot.output_transition_id,
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

    # Step 7: close session
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    closed_session = GitSession(
        session_id=session.session_id,
        run_id=session.run_id,
        input_transition_id=session.input_transition_id,
        repo_root=session.repo_root,
        base_commit=session.base_commit,
        base_branch=session.base_branch,
        base_dirty=session.base_dirty,
        started_at=session.started_at,
        started_by=session.started_by,
        closed_at=now,
        closed_by=user_id,
        output_transition_id=ot.output_transition_id,
        metadata=dict(session.metadata),
    )
    save_session(closed_session, run_dir)

    # Step 8: clear current pointer if it points to this session
    clear_current_pointer(session_id, run_dir)

    return {
        "created": {
            "output_transition_id": ot.output_transition_id,
            "result_payload_id": result_pl_id,
            "git_change_payload_id": git_payload_id_tentative,
        },
        "linked": {
            "input_transition_id": it_id,
            "matched_prediction_output_id": matched_prediction_output_id,
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
            f"stag trace --from-node {handle.run_graph.output_transitions[ot.output_transition_id].to_node_id}",
            f"stag git diff --output-transition {ot.output_transition_id}",
        ],
    }


def git_finish_form_b(
    handle: RunHandle,
    run_dir: Path,
    session_id: str,
    *,
    output_transition_id: str,
    user_id: str = "user",
) -> dict:
    """Form B: attach GitChangePayload to an existing observed OT.

    Returns a result dict with created IDs, git info, warnings, and next hints.
    """
    # 1. Load session
    session = load_session(session_id, run_dir)

    # Validation checks 1-5
    _validate_session(session, handle)

    it_id = session.input_transition_id

    # 9. OT exists
    if output_transition_id not in handle.run_graph.output_transitions:
        raise KeyError(f"unknown output_transition_id: {output_transition_id}")

    # 10. OT's IT matches session
    ot = handle.run_graph.output_transitions[output_transition_id]
    if ot.input_transition_id != it_id:
        raise ValueError(
            f"output_transition {output_transition_id} belongs to input_transition "
            f"{ot.input_transition_id!r}, not session IT {it_id!r}"
        )

    # 11. OT is active
    if is_inactive_output_transition(handle.run_graph, output_transition_id):
        raise ValueError(f"output_transition {output_transition_id} is inactive (cut)")

    # 12. OT has ResultPayload
    result_payloads = handle.run_graph.payloads_for_output_transition(
        output_transition_id, payload_type="result"
    )
    if not result_payloads:
        raise ValueError(
            f"output_transition {output_transition_id} has no ResultPayload. "
            "Form B only supports observed (result) OutputTransitions."
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
    existing_gcp = handle.run_graph.payloads_for_output_transition(
        output_transition_id, payload_type="git_change"
    )
    if existing_gcp:
        warnings.append(
            f"OutputTransition {output_transition_id} already has "
            f"{len(existing_gcp)} GitChangePayload(s). Attaching another is allowed "
            "but unusual."
        )

    # Parallel session warning
    from stag.core.git.session import list_sessions
    for s in list_sessions(run_dir):
        if (
            s.input_transition_id == it_id
            and s.is_open
            and s.session_id != session_id
        ):
            warnings.append(
                f"Another open GitSession ({s.session_id}) is tracking the same "
                f"InputTransition {it_id}."
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
    pl_count = handle._counters.get("pl", 0) + 1
    handle._counters["pl"] = pl_count
    from stag.core.ids import sequential_id
    git_payload_id = sequential_id("pl", pl_count)

    patch_artifact: str | None = None
    if gdata["patch_text"]:
        patch_artifact = _write_patch_artifact(gdata["patch_text"], git_payload_id, run_dir)

    # Attach GitChangePayload
    gcp = GitChangePayload(
        payload_id=git_payload_id,
        target_id=output_transition_id,
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

    # Close session
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    closed_session = GitSession(
        session_id=session.session_id,
        run_id=session.run_id,
        input_transition_id=session.input_transition_id,
        repo_root=session.repo_root,
        base_commit=session.base_commit,
        base_branch=session.base_branch,
        base_dirty=session.base_dirty,
        started_at=session.started_at,
        started_by=session.started_by,
        closed_at=now,
        closed_by=user_id,
        output_transition_id=output_transition_id,
        metadata=dict(session.metadata),
    )
    save_session(closed_session, run_dir)

    # Clear current pointer if applicable
    clear_current_pointer(session_id, run_dir)

    return {
        "created": {
            "output_transition_id": None,
            "result_payload_id": None,
            "git_change_payload_id": git_payload_id,
        },
        "linked": {
            "input_transition_id": it_id,
            "matched_prediction_output_id": None,
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
            f"stag git diff --output-transition {output_transition_id}",
        ],
    }
