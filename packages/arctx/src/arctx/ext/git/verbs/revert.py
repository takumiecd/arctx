"""RunHandle.git.revert implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from arctx.core.schema.graph import Step
from arctx.ext.git.helpers.repo import resolve_worktree_path
from arctx.ext.git.payloads import RevertPayload
from arctx.ext.git.queries import current_sha, step_by_sha
from arctx.ext.git.registry import resolve_repo_id
from arctx.ext.git.verbs._forward_step import (
    capture_git_info,
    check_branch_tip_consistency,
    resolve_current_branch,
    resolve_current_node_ids,
)


def revert_impl(
    self,
    *,
    target_sha: str | None = None,
    target_step: str | None = None,
    message: str | None = None,
    branch: str | None = None,
    repo_path: Path | None = None,
    user_id: str | None = None,
    lane_id: str | None = None,
    head_commit: str | None = None,
    dry_run: bool = False,
) -> Step:
    """Drive ``git revert <sha>`` and record the corresponding arctx Step."""
    resolved_repo_path: Path = resolve_worktree_path(repo_path)

    if target_sha is None and target_step is None:
        raise ValueError("Either target_sha or target_step must be provided.")
    if target_sha is not None and target_step is not None:
        raise ValueError("target_sha and target_step are mutually exclusive.")

    reverted_step_id: str
    reverted_commit: str

    if target_step is not None:
        if target_step not in self.run_graph.steps:
            raise KeyError(f"unknown step_id: {target_step}")
        sha = current_sha(self.run_graph, target_step)
        if sha is None:
            raise ValueError(
                f"step {target_step!r} has no GitChangePayload / sha"
            )
        reverted_commit = sha
        reverted_step_id = target_step
    else:
        assert target_sha is not None
        reverted_commit = target_sha
        found = step_by_sha(self.run_graph, target_sha)
        if found is None:
            raise KeyError(
                f"no arctx step found for sha {target_sha!r}; "
                "ensure the commit was recorded via 'arctx commit' first"
            )
        reverted_step_id = found

    current_node_ids = resolve_current_node_ids(self, lane_id)

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

    repo_id = "" if dry_run else resolve_repo_id(self, resolved_repo_path)

    if lane_id is not None:
        check_branch_tip_consistency(
            self.run_graph, current_branch, current_node_ids, repo_id
        )

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

    if user_id is not None and lane_id is not None:
        self.ensure_lane(user_id=user_id, lane_id=lane_id)

    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    step_id = self._next_id("t")
    from arctx.core.schema.graph import Step as _Step  # noqa: PLC0415
    step = _Step(
        step_id=step_id,
        input_node_ids=current_node_ids,
        output_node_id=output_node.node_id,
    )
    self.run_graph.add_step(step)

    branch_payload = BranchPayload(
        payload_id=self._next_id("pl"),
        target_id=step_id,
        branch=current_branch,
        repo_id=repo_id,
    )
    self.run_graph.attach_payload(branch_payload)

    git_payload = GitChangePayload(
        payload_id=self._next_id("pl"),
        target_id=step_id,
        branch=current_branch,
        head_commit=head_commit,
        diff_summary=diff_summary,
        commit_log=commit_log,
        repo_id=repo_id,
    )
    self.run_graph.attach_payload(git_payload)

    revert_payload = RevertPayload(
        payload_id=self._next_id("pl"),
        target_id=step_id,
        reverted_step=reverted_step_id,
        reverted_commit=reverted_commit,
    )
    self.run_graph.attach_payload(revert_payload)

    if user_id is not None and lane_id is not None:
        tip_event = make_branch_tip_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            lane_id=lane_id,
            user_id=user_id,
            branch=current_branch,
            tip_node_id=output_node.node_id,
            repo_id=repo_id,
        )
        self.run_graph.add_work_event(tip_event)

        sp_event = make_session_pointer_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            lane_id=lane_id,
            user_id=user_id,
            current_node_ids=(output_node.node_id,),
            current_branch=current_branch,
        )
        self.run_graph.add_work_event(sp_event)

    self.record_work_event(
        user_id=user_id,
        lane_id=lane_id,
        event_type="revert_created",
        target_kind="step",
        target_id=step_id,
        created_records=(
            output_node.node_id,
            step_id,
            branch_payload.payload_id,
            git_payload.payload_id,
            revert_payload.payload_id,
        ),
        summary=f"revert {reverted_commit[:12]}",
        data={
            "reverted_step": reverted_step_id,
            "reverted_commit": reverted_commit,
            "branch": current_branch,
            "head_commit": head_commit,
        },
    )

    return step
