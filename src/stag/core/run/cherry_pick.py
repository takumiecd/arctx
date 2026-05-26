"""RunHandle.cherry_pick implementation.

Drives a ``git cherry-pick <sha>`` and records the corresponding stag
Transition with BranchPayload, GitChangePayload, CherryPickPayload,
BranchTipEvent, and SessionPointerEvent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from stag.core.schema.graph import Node, Transition
from stag.core.schema.payloads import BranchPayload, CherryPickPayload, GitChangePayload
from stag.core.run._forward_transition import (
    capture_git_info,
    check_branch_tip_consistency,
    resolve_current_branch,
    resolve_current_node_ids,
)
from stag.core.schema.work_helpers import (
    make_branch_tip_event,
    make_session_pointer_event,
)


def cherry_pick_impl(
    self,
    *,
    source_sha: str,
    branch: str | None = None,
    repo_path: Path | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
    head_commit: str | None = None,
    dry_run: bool = False,
) -> Transition:
    """Drive ``git cherry-pick <sha>`` and record the corresponding stag Transition.

    Steps:
    1. Resolve current_node_ids and current_branch.
    2. Look up the source stag Transition via transition_by_sha (may be None for
       cross-repo cherry-picks).
    3. Run ``git cherry-pick <source_sha>`` (unless dry_run).
    4. Capture head_commit, diff_summary, commit_log from git.
    5. Append:
       - new Node + Transition(input=current_node_ids, output=new Node)
       - BranchPayload(branch=current_branch)
       - GitChangePayload(head_commit=<cherry-pick commit>)
       - CherryPickPayload(source_transition=<lookup>, source_commit=source_sha)
       - BranchTipEvent, SessionPointerEvent
    6. Return the new Transition.

    Parameters
    ----------
    source_sha:
        Commit SHA to cherry-pick.
    branch:
        Override branch name.
    repo_path:
        Path to git repo root. Defaults to cwd.
    user_id:
        User ID for attribution.
    work_session_id:
        Work session ID.
    head_commit:
        Override HEAD SHA after cherry-pick (for dry_run / testing).
    dry_run:
        If True, skip the actual git call.

    Returns
    -------
    The newly created Transition.
    """
    resolved_repo_path: Path = repo_path or Path.cwd()

    # ------------------------------------------------------------------
    # 1. Resolve current_node_ids (single-input only; merge is S7).
    # ------------------------------------------------------------------
    current_node_ids = resolve_current_node_ids(self, work_session_id)

    if len(current_node_ids) != 1:
        raise NotImplementedError(
            "cherry_pick supports single-input only. Multi-input (merge/join) is S7."
        )

    for nid in current_node_ids:
        self._ensure_active_node(nid)

    # ------------------------------------------------------------------
    # 2. Resolve current_branch.
    # ------------------------------------------------------------------
    current_branch = resolve_current_branch(
        branch=branch,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    # ------------------------------------------------------------------
    # 2b. Parallel-session guard (§7.2).
    # Only enforced when a work session is tracked.
    # ------------------------------------------------------------------
    if work_session_id is not None:
        check_branch_tip_consistency(self.run_graph, current_branch, current_node_ids)

    # ------------------------------------------------------------------
    # 3. Look up source transition (best-effort; None is OK for cross-repo).
    # ------------------------------------------------------------------
    source_transition_id: str | None = self.run_graph.transition_by_sha(source_sha)

    # ------------------------------------------------------------------
    # 4. Run git cherry-pick (unless dry_run).
    # ------------------------------------------------------------------
    if not dry_run:
        cmd = ["git", "cherry-pick", source_sha]
        result = subprocess.run(
            cmd,
            cwd=str(resolved_repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                result.stdout,
                result.stderr,
            )

    # ------------------------------------------------------------------
    # 5. Capture git info.
    # ------------------------------------------------------------------
    if head_commit is None:
        if dry_run:
            head_commit = "dry_run_cp_sha_" + self._next_id("sha")
        else:
            from stag.core.git import repo as git_repo  # noqa: PLC0415
            head_commit = git_repo.current_commit(resolved_repo_path)

    diff_summary, commit_log = capture_git_info(
        head_commit=head_commit,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    # ------------------------------------------------------------------
    # 6. Append graph records.
    # ------------------------------------------------------------------
    if user_id is not None and work_session_id is not None:
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)

    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    transition_id = self._next_id("t")
    transition = Transition(
        transition_id=transition_id,
        input_node_ids=current_node_ids,
        output_node_id=output_node.node_id,
    )
    self.run_graph.add_transition(transition)

    branch_payload = BranchPayload(
        payload_id=self._next_id("pl"),
        target_id=transition_id,
        branch=current_branch,
    )
    self.run_graph.attach_payload(branch_payload)

    git_payload = GitChangePayload(
        payload_id=self._next_id("pl"),
        target_id=transition_id,
        branch=current_branch,
        head_commit=head_commit,
        diff_summary=diff_summary,
        commit_log=commit_log,
    )
    self.run_graph.attach_payload(git_payload)

    cp_payload = CherryPickPayload(
        payload_id=self._next_id("pl"),
        target_id=transition_id,
        source_transition=source_transition_id,
        source_commit=source_sha,
    )
    self.run_graph.attach_payload(cp_payload)

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

        sp_event = make_session_pointer_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            current_node_ids=(output_node.node_id,),
            current_branch=current_branch,
        )
        self.run_graph.add_work_event(sp_event)

    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="cherry_pick_created",
        target_kind="transition",
        target_id=transition_id,
        created_records=(
            output_node.node_id,
            transition_id,
            branch_payload.payload_id,
            git_payload.payload_id,
            cp_payload.payload_id,
        ),
        summary=f"cherry-pick {source_sha[:12]}",
        data={
            "source_sha": source_sha,
            "source_transition": source_transition_id,
            "branch": current_branch,
            "head_commit": head_commit,
        },
    )

    return transition
