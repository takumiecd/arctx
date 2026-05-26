"""RunHandle.commit implementation.

Drives a git commit and records the corresponding stag Transition with
BranchPayload, GitChangePayload, BranchTipEvent, and SessionPointerEvent.

S2 scope: single-input commit only (merge / join is S7).
Parallel-session guard (§7.2) is TODO for S9.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from stag.core.schema.graph import Node, Transition
from stag.core.schema.payloads import BranchPayload, CommitEntry, DiffSummary, GitChangePayload
from stag.core.schema.work_helpers import (
    BRANCH_TIP_EVENT,
    SESSION_POINTER_EVENT,
    latest_session_pointer,
    make_branch_tip_event,
    make_session_pointer_event,
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
    """Drive a git commit and record the corresponding stag Transition.

    Steps (per REDESIGN §9.1):
    1. Resolve current_node_ids from the latest SessionPointerEvent.
       Falls back to (root_node,) if no SessionPointerEvent exists yet.
    2. Resolve current_branch (argument → git current branch).
    3. Run ``git commit -m message`` (unless dry_run=True).
    4. Capture head_commit, diff_summary, commit_log from git.
    5. Append:
       - new Node + Transition(input=current_node_ids, output=new Node)
       - BranchPayload(transition, branch=current_branch)
       - GitChangePayload(transition, branch, head_commit, diff_summary, commit_log)
       - BranchTipEvent(branch=current_branch, tip_node_id=<new node>)
       - SessionPointerEvent(current_node_ids=(<new node>,), current_branch=current_branch)
    6. Return the new Transition.

    Parameters
    ----------
    message:
        Commit message passed to ``git commit -m``.
    branch:
        Override the branch name. If None, inferred from git.
    repo_path:
        Path to the git repo root. Defaults to cwd.
    user_id:
        User ID for attribution. If None, work events are not recorded.
    work_session_id:
        Work session ID. If None, work events are not recorded.
    head_commit:
        Override the HEAD commit SHA (for testing / dry-run). If None
        and dry_run is False, git is queried for the HEAD SHA after commit.
    dry_run:
        If True, skip the actual ``git commit`` call. Useful for testing
        without a real git repository.

    Returns
    -------
    The newly created Transition.

    Notes
    -----
    TODO (S9): Add parallel-session guard. Before committing, verify that
    the latest BranchTipEvent.tip_node_id for current_branch is in
    current_node_ids. If not, reject with a non-fast-forward error.
    """
    resolved_repo_path: Path = repo_path or Path.cwd()

    # ------------------------------------------------------------------
    # 1. Resolve current_node_ids.
    # ------------------------------------------------------------------
    current_node_ids: tuple[str, ...]
    if work_session_id is not None:
        sp_event = latest_session_pointer(self.run_graph, work_session_id)
        if sp_event is not None:
            raw = sp_event.data.get("current_node_ids") or []
            current_node_ids = tuple(str(n) for n in raw)
        else:
            current_node_ids = (self.root_node_id,)
    else:
        current_node_ids = (self.root_node_id,)

    # S2: single-input only. Multi-input is S7.
    if len(current_node_ids) != 1:
        raise NotImplementedError(
            "S2 supports single-input commits only. "
            "Multi-input (merge/join) is implemented in S7."
        )

    for nid in current_node_ids:
        self._ensure_active_node(nid)

    # ------------------------------------------------------------------
    # 2. Resolve current_branch.
    # ------------------------------------------------------------------
    current_branch: str | None = branch
    if current_branch is None and not dry_run:
        from stag.core.git import repo as git_repo  # noqa: PLC0415
        current_branch = git_repo.current_branch(resolved_repo_path)
    if current_branch is None:
        current_branch = "unknown"

    # ------------------------------------------------------------------
    # 3. Run git commit (unless dry_run).
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 4. Capture git info.
    # ------------------------------------------------------------------
    if head_commit is None:
        if dry_run:
            head_commit = "dry_run_sha_" + self._next_id("sha")
        else:
            from stag.core.git import repo as git_repo  # noqa: PLC0415
            head_commit = git_repo.current_commit(resolved_repo_path)

    diff_summary = DiffSummary(files_changed=0, insertions=0, deletions=0)
    commit_log: tuple[CommitEntry, ...] = ()

    if not dry_run:
        from stag.core.git import repo as git_repo  # noqa: PLC0415
        try:
            raw_log = git_repo.commit_log_for_commits(resolved_repo_path, [head_commit])
            commit_log = tuple(
                CommitEntry(
                    sha=e["sha"],
                    subject=e["subject"],
                    author=e["author"],
                    date=e["date"],
                )
                for e in raw_log
            )
        except Exception:
            pass

        try:
            # Use shortstat from HEAD~1 to HEAD when possible.
            stat_result = subprocess.run(
                ["git", "diff", "--shortstat", "HEAD~1", "HEAD"],
                cwd=str(resolved_repo_path),
                capture_output=True,
                text=True,
            )
            if stat_result.returncode == 0 and stat_result.stdout.strip():
                import re  # noqa: PLC0415
                raw = stat_result.stdout.strip()
                fc = re.search(r"(\d+) files? changed", raw)
                ins = re.search(r"(\d+) insertion", raw)
                dls = re.search(r"(\d+) deletion", raw)
                diff_summary = DiffSummary(
                    files_changed=int(fc.group(1)) if fc else 0,
                    insertions=int(ins.group(1)) if ins else 0,
                    deletions=int(dls.group(1)) if dls else 0,
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 5. Append graph records.
    # ------------------------------------------------------------------
    # Ensure work session exists before recording events.
    if user_id is not None and work_session_id is not None:
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)

    # new Node.
    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    # new Transition.
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

    # BranchTipEvent.
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

        # SessionPointerEvent.
        sp_event = make_session_pointer_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            current_node_ids=(output_node.node_id,),
            current_branch=current_branch,
        )
        self.run_graph.add_work_event(sp_event)

    # Work event for audit trail.
    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="commit_created",
        target_kind="transition",
        target_id=transition_id,
        created_records=(
            output_node.node_id,
            transition_id,
            branch_payload.payload_id,
            git_payload.payload_id,
        ),
        summary=message,
        data={
            "message": message,
            "branch": current_branch,
            "head_commit": head_commit,
        },
    )

    return transition
