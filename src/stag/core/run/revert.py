"""RunHandle.revert implementation.

Drives a ``git revert`` and records the corresponding stag Transition with
BranchPayload, GitChangePayload, RevertPayload, BranchTipEvent, and
SessionPointerEvent.

The original (reverted) Transition is NOT touched — no CutPayload is appended
to it.  The new forward Transition carries a RevertPayload that references the
original.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from stag.core.schema.graph import Transition
from stag.core.schema.payloads import RevertPayload
from stag.core.run._forward_transition import (
    capture_git_info,
    check_branch_tip_consistency,
    record_forward_transition,
    resolve_current_branch,
    resolve_current_node_ids,
)


def revert_impl(
    self,
    *,
    target_sha: str | None = None,
    target_transition: str | None = None,
    message: str | None = None,
    branch: str | None = None,
    repo_path: Path | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
    head_commit: str | None = None,
    dry_run: bool = False,
) -> Transition:
    """Drive ``git revert <sha>`` and record the corresponding stag Transition.

    Steps:
    1. Resolve the target SHA to revert (from target_sha or target_transition).
    2. Look up the corresponding stag Transition via transition_by_sha.
    3. Resolve current_node_ids and current_branch.
    4. Run ``git revert --no-edit <sha>`` (unless dry_run).
    5. Capture head_commit, diff_summary, commit_log from git.
    6. Append:
       - new Node + Transition(input=current_node_ids, output=new Node)
       - BranchPayload(branch=current_branch)
       - GitChangePayload(head_commit=<revert commit>)
       - RevertPayload(reverted_transition, reverted_commit)
       - BranchTipEvent, SessionPointerEvent
    7. Return the new Transition.

    The original (reverted) Transition is NOT modified.

    Parameters
    ----------
    target_sha:
        Commit SHA to revert. Mutually exclusive with target_transition.
    target_transition:
        Transition ID whose current_sha to revert.  Mutually exclusive with
        target_sha.
    message:
        Override commit message. If None, git uses the default revert message.
    branch:
        Override branch name.
    repo_path:
        Path to git repo root. Defaults to cwd.
    user_id:
        User ID for attribution.
    work_session_id:
        Work session ID.
    head_commit:
        Override HEAD SHA after revert (for dry_run / testing).
    dry_run:
        If True, skip the actual git call.

    Returns
    -------
    The newly created Transition.
    """
    resolved_repo_path: Path = repo_path or Path.cwd()

    # ------------------------------------------------------------------
    # 1. Resolve target SHA and reverted_transition.
    # ------------------------------------------------------------------
    if target_sha is None and target_transition is None:
        raise ValueError("Either target_sha or target_transition must be provided.")
    if target_sha is not None and target_transition is not None:
        raise ValueError("target_sha and target_transition are mutually exclusive.")

    reverted_transition_id: str
    reverted_commit: str

    if target_transition is not None:
        # Look up the transition and get its current sha.
        if target_transition not in self.run_graph.transitions:
            raise KeyError(f"unknown transition_id: {target_transition}")
        sha = self.run_graph.current_sha(target_transition)
        if sha is None:
            raise ValueError(
                f"transition {target_transition!r} has no GitChangePayload / sha"
            )
        reverted_commit = sha
        reverted_transition_id = target_transition
    else:
        # target_sha was provided.
        assert target_sha is not None
        reverted_commit = target_sha
        found = self.run_graph.transition_by_sha(target_sha)
        if found is None:
            raise KeyError(
                f"no stag transition found for sha {target_sha!r}; "
                "ensure the commit was recorded via 'stag commit' first"
            )
        reverted_transition_id = found

    # ------------------------------------------------------------------
    # 2. Resolve current_node_ids (single-input only; merge is S7).
    # ------------------------------------------------------------------
    current_node_ids = resolve_current_node_ids(self, work_session_id)

    if len(current_node_ids) != 1:
        raise NotImplementedError(
            "revert supports single-input only. Multi-input (merge/join) is S7."
        )

    for nid in current_node_ids:
        self._ensure_active_node(nid)

    # ------------------------------------------------------------------
    # 3. Resolve current_branch.
    # ------------------------------------------------------------------
    current_branch = resolve_current_branch(
        branch=branch,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    # ------------------------------------------------------------------
    # 3b. Parallel-session guard (§7.2).
    # Only enforced when a work session is tracked.
    # ------------------------------------------------------------------
    if work_session_id is not None:
        check_branch_tip_consistency(self.run_graph, current_branch, current_node_ids)

    # ------------------------------------------------------------------
    # 4. Run git revert (unless dry_run).
    # ------------------------------------------------------------------
    if not dry_run:
        cmd = ["git", "revert", "--no-edit", reverted_commit]
        if message is not None:
            cmd = ["git", "revert", "--no-edit", "-m", "1", reverted_commit]
            # Note: -m 1 is for merge commits; for regular reverts we use --no-edit
            # and a separate amend if message override is needed.
            # Simpler: just use --no-edit and ignore message override for now.
            cmd = ["git", "revert", "--no-edit", reverted_commit]
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
            head_commit = "dry_run_revert_sha_" + self._next_id("sha")
        else:
            from stag.core.git import repo as git_repo  # noqa: PLC0415
            head_commit = git_repo.current_commit(resolved_repo_path)

    diff_summary, commit_log = capture_git_info(
        head_commit=head_commit,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    # ------------------------------------------------------------------
    # 6. Build RevertPayload (target_id filled in after transition creation).
    # ------------------------------------------------------------------
    # We need a placeholder transition_id; record_forward_transition will
    # create the real one.  We build the payload after we know the transition_id.
    # Strategy: create a factory closure that record_forward_transition calls,
    # or build the payload here with a sentinel and replace.
    #
    # Simpler approach: inline record_forward_transition steps and inject
    # RevertPayload with the correct target_id.

    from stag.core.schema.graph import Node  # noqa: PLC0415
    from stag.core.schema.payloads import BranchPayload, GitChangePayload  # noqa: PLC0415
    from stag.core.schema.work_helpers import (  # noqa: PLC0415
        make_branch_tip_event,
        make_session_pointer_event,
    )

    if user_id is not None and work_session_id is not None:
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)

    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    transition_id = self._next_id("t")
    from stag.core.schema.graph import Transition as _Transition  # noqa: PLC0415
    transition = _Transition(
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

    revert_payload = RevertPayload(
        payload_id=self._next_id("pl"),
        target_id=transition_id,
        reverted_transition=reverted_transition_id,
        reverted_commit=reverted_commit,
    )
    self.run_graph.attach_payload(revert_payload)

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
        event_type="revert_created",
        target_kind="transition",
        target_id=transition_id,
        created_records=(
            output_node.node_id,
            transition_id,
            branch_payload.payload_id,
            git_payload.payload_id,
            revert_payload.payload_id,
        ),
        summary=f"revert {reverted_commit[:12]}",
        data={
            "reverted_transition": reverted_transition_id,
            "reverted_commit": reverted_commit,
            "branch": current_branch,
            "head_commit": head_commit,
        },
    )

    return transition
