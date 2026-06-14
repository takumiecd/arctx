"""arctx git start implementation."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from arctx.core.cuts import is_inactive_step
from arctx.ext.git.helpers import repo as git_repo
from arctx.ext.git.helpers.session import (
    GitSession,
    clear_current_pointer,
    list_sessions,
    load_current_pointer,
    save_current_pointer,
    save_session,
)
from arctx.core.ids import opaque_id
from arctx.core.run.handle import RunHandle


def git_start(
    handle: RunHandle,
    run_dir: Path,
    step_id: str,
    *,
    repo_root_hint: Path | None = None,
    user_id: str = "user",
) -> dict:
    """Create a GitSession for *step_id*.

    Returns a dict with ``session_id``, ``step_id``,
    ``base_commit``, ``branch``, ``dirty``, ``warnings``, and ``next``.

    Raises
    ------
    KeyError
        If *step_id* is not found in the graph.
    ValueError
        If the IT is inactive, HEAD is detached, or the repo root cannot be
        detected.
    """
    if step_id not in handle.run_graph.steps:
        raise KeyError(f"unknown step_id: {step_id}")
    if is_inactive_step(handle.run_graph, step_id):
        raise ValueError(f"step is inactive (cut): {step_id}")

    # 2. Detect repo root
    cwd = repo_root_hint or Path(".")
    try:
        repo_root = git_repo.find_repo_root(cwd)
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            "could not detect a git repository from the current directory. "
            "Run from inside a git repo."
        ) from exc

    # 3. Detached HEAD check
    branch = git_repo.current_branch(repo_root)
    if branch is None:
        raise ValueError("HEAD is detached. Checkout a branch before running 'arctx git start'.")

    # 4. Commit and dirty state
    base_commit = git_repo.current_commit(repo_root)
    dirty = git_repo.is_dirty(repo_root)

    # 5. Mint session_id using handle counter style
    session_id = opaque_id("gs")

    # 6. Collect warnings
    warnings: list[str] = []
    if dirty:
        warnings.append(
            "Working tree has uncommitted tracked-file changes. "
            "Those changes may be included in the final GitChangePayload "
            "if they are committed before 'arctx git finish'."
        )

    # Check for parallel open sessions on the same IT
    existing_sessions = list_sessions(run_dir)
    for s in existing_sessions:
        if s.step_id == step_id and s.is_open and s.session_id != session_id:
            warnings.append(
                f"Another open GitSession ({s.session_id}) is already tracking "
                f"step {step_id}. "
                "Multiple sessions on the same IT are allowed but unusual."
            )
            break

    # 7. Create and save session
    now = datetime.now(timezone.utc).isoformat()
    session = GitSession(
        session_id=session_id,
        run_id=handle.run_id,
        step_id=step_id,
        repo_root=str(repo_root),
        base_commit=base_commit,
        base_branch=branch,
        base_dirty=dirty,
        started_at=now,
        started_by=user_id,
    )
    save_session(session, run_dir)

    # 8. Update current.json
    save_current_pointer(session_id, run_dir)

    return {
        "session_id": session_id,
        "step_id": step_id,
        "base_commit": base_commit,
        "branch": branch,
        "dirty": dirty,
        "warnings": warnings,
        "next": [
            f"arctx git diff {session_id}",
            f"arctx git finish {session_id} --status completed",
        ],
    }
