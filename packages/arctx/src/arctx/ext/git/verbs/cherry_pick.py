"""RunHandle.git.cherry_pick implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from arctx.core.schema.graph import Node, Step
from arctx.core.schema.work_helpers import make_session_pointer_event
from arctx.ext.git.events import make_branch_tip_event
from arctx.ext.git.helpers.repo import resolve_worktree_path
from arctx.ext.git.payloads import BranchPayload, CherryPickPayload, GitChangePayload
from arctx.ext.git.queries import step_by_sha
from arctx.ext.git.registry import resolve_repo_id
from arctx.ext.git.verbs._forward_step import (
    capture_git_info,
    check_branch_tip_consistency,
    resolve_current_branch,
    resolve_current_node_ids,
)


def cherry_pick_impl(
    self,
    *,
    source_sha: str,
    branch: str | None = None,
    repo_path: Path | None = None,
    user_id: str | None = None,
    lane_id: str | None = None,
    head_commit: str | None = None,
    dry_run: bool = False,
) -> Step:
    """Drive ``git cherry-pick <sha>`` and record the corresponding arctx Step."""
    resolved_repo_path: Path = resolve_worktree_path(repo_path)

    current_node_ids = resolve_current_node_ids(self, lane_id)

    if len(current_node_ids) != 1:
        raise NotImplementedError(
            "cherry_pick supports single-input only. Multi-input (merge/join) is S7."
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

    source_step_id: str | None = step_by_sha(self.run_graph, source_sha)

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

    if head_commit is None:
        if dry_run:
            head_commit = "dry_run_cp_sha_" + self._next_id("sha")
        else:
            from arctx.ext.git.helpers import repo as git_repo  # noqa: PLC0415
            head_commit = git_repo.current_commit(resolved_repo_path)

    diff_summary, commit_log = capture_git_info(
        head_commit=head_commit,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    if user_id is not None and lane_id is not None:
        self.ensure_lane(user_id=user_id, lane_id=lane_id)

    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    step_id = self._next_id("t")
    step = Step(
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

    cp_payload = CherryPickPayload(
        payload_id=self._next_id("pl"),
        target_id=step_id,
        source_step=source_step_id,
        source_commit=source_sha,
    )
    self.run_graph.attach_payload(cp_payload)

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
        event_type="cherry_pick_created",
        target_kind="step",
        target_id=step_id,
        created_records=(
            output_node.node_id,
            step_id,
            branch_payload.payload_id,
            git_payload.payload_id,
            cp_payload.payload_id,
        ),
        summary=f"cherry-pick {source_sha[:12]}",
        data={
            "source_sha": source_sha,
            "source_step": source_step_id,
            "branch": current_branch,
            "head_commit": head_commit,
        },
    )

    return step
