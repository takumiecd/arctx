"""RunHandle.git.revert implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from arctx.core.schema.graph import Transition
from arctx.ext.git.helpers.repo import resolve_worktree_path
from arctx.ext.git.payloads import RevertPayload
from arctx.ext.git.queries import current_sha, transition_by_sha
from arctx.ext.git.verbs._forward_transition import (
    capture_git_info,
    check_branch_tip_consistency,
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
    """Drive ``git revert <sha>`` and record the corresponding arctx Transition."""
    resolved_repo_path: Path = resolve_worktree_path(repo_path)

    if target_sha is None and target_transition is None:
        raise ValueError("Either target_sha or target_transition must be provided.")
    if target_sha is not None and target_transition is not None:
        raise ValueError("target_sha and target_transition are mutually exclusive.")

    reverted_transition_id: str
    reverted_commit: str

    if target_transition is not None:
        if target_transition not in self.run_graph.transitions:
            raise KeyError(f"unknown transition_id: {target_transition}")
        sha = current_sha(self.run_graph, target_transition)
        if sha is None:
            raise ValueError(
                f"transition {target_transition!r} has no GitChangePayload / sha"
            )
        reverted_commit = sha
        reverted_transition_id = target_transition
    else:
        assert target_sha is not None
        reverted_commit = target_sha
        found = transition_by_sha(self.run_graph, target_sha)
        if found is None:
            raise KeyError(
                f"no arctx transition found for sha {target_sha!r}; "
                "ensure the commit was recorded via 'arctx commit' first"
            )
        reverted_transition_id = found

    current_node_ids = resolve_current_node_ids(self, work_session_id)

    if len(current_node_ids) != 1:
        raise NotImplementedError(
            "revert supports single-input only. Multi-input (merge/join) is S7."
        )

    for nid in current_node_ids:
        self._ensure_active_node(nid)

    current_branch = resolve_current_branch(
        branch=branch,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    if work_session_id is not None:
        check_branch_tip_consistency(self.run_graph, current_branch, current_node_ids)

    if not dry_run:
        cmd = ["git", "revert", "--no-edit", reverted_commit]
        if message is not None:
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

    if head_commit is None:
        if dry_run:
            head_commit = "dry_run_revert_sha_" + self._next_id("sha")
        else:
            from arctx.ext.git.helpers import repo as git_repo  # noqa: PLC0415
            head_commit = git_repo.current_commit(resolved_repo_path)

    diff_summary, commit_log = capture_git_info(
        head_commit=head_commit,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    from arctx.core.schema.graph import Node  # noqa: PLC0415
    from arctx.core.schema.work_helpers import make_session_pointer_event  # noqa: PLC0415
    from arctx.ext.git.events import (  # noqa: PLC0415
        make_branch_tip_event,
    )
    from arctx.ext.git.payloads import BranchPayload, GitChangePayload  # noqa: PLC0415

    if user_id is not None and work_session_id is not None:
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)

    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    transition_id = self._next_id("t")
    from arctx.core.schema.graph import Transition as _Transition  # noqa: PLC0415
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
