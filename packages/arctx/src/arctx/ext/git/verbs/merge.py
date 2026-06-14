"""RunHandle.git.merge implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from arctx.core.schema.graph import Step
from arctx.core.schema.payloads import JoinPayload
from arctx.ext.git.payloads import MergePayload
from arctx.ext.git.helpers.repo import resolve_worktree_path
from arctx.ext.git.verbs._forward_step import (
    capture_git_info,
    check_branch_tip_consistency,
    record_forward_step,
    resolve_current_branch,
    resolve_current_node_ids,
)
from arctx.ext.git.events import latest_branch_tip
from arctx.ext.git.registry import resolve_repo_id

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle


def _resolve_other_node_id(
    self: "RunHandle",
    *,
    other_node_id: str | None,
    other_branch: str | None,
    work_session_id: str | None,
    repo_id: str = "",
) -> str:
    if other_node_id is not None:
        return other_node_id

    if other_branch is None:
        raise ValueError(
            "merge_impl requires either other_node_id or other_branch"
        )

    tip_event = latest_branch_tip(self.run_graph, other_branch, repo_id)
    if tip_event is not None:
        tip_id = tip_event.data.get("tip_node_id")
        if tip_id:
            return str(tip_id)

    raise ValueError(
        f"cannot resolve tip node for branch {other_branch!r}: "
        "no BranchTipEvent found. Pass other_node_id explicitly."
    )


def merge_impl(
    self: "RunHandle",
    *,
    other_node_id: str | None = None,
    other_branch: str | None = None,
    message: str | None = None,
    branch: str | None = None,
    repo_path: Path | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
    head_commit: str | None = None,
    dry_run: bool = False,
    join: bool = False,
) -> Step:
    """Drive ``git merge <other>`` and record a multi-input Step."""
    resolved_repo_path: Path = resolve_worktree_path(repo_path)

    repo_id = "" if dry_run else resolve_repo_id(self, resolved_repo_path)

    current_node_ids = resolve_current_node_ids(self, work_session_id)

    for nid in current_node_ids:
        self._ensure_active_node(nid)

    resolved_other_node_id = _resolve_other_node_id(
        self,
        other_node_id=other_node_id,
        other_branch=other_branch,
        work_session_id=work_session_id,
        repo_id=repo_id,
    )
    self._ensure_active_node(resolved_other_node_id)

    seen: set[str] = set()
    merged_inputs: list[str] = []
    for nid in (*current_node_ids, resolved_other_node_id):
        if nid not in seen:
            seen.add(nid)
            merged_inputs.append(nid)
    multi_input_node_ids = tuple(merged_inputs)

    current_branch = resolve_current_branch(
        branch=branch,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    if work_session_id is not None:
        check_branch_tip_consistency(
            self.run_graph, current_branch, current_node_ids, repo_id
        )

    if not dry_run:
        merge_target = other_branch or resolved_other_node_id
        git_cmd = ["git", "merge"]
        if message is not None:
            git_cmd += ["-m", message]
        git_cmd.append(str(merge_target))

        result = subprocess.run(
            git_cmd,
            cwd=str(resolved_repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                git_cmd,
                result.stdout,
                result.stderr,
            )

    if head_commit is None:
        if dry_run:
            head_commit = "dry_run_merge_sha_" + self._next_id("sha")
        else:
            from arctx.ext.git.helpers import repo as git_repo  # noqa: PLC0415
            head_commit = git_repo.current_commit(resolved_repo_path)

    diff_summary, commit_log = capture_git_info(
        head_commit=head_commit,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    merged_from_label = other_branch or resolved_other_node_id
    merged_into_label = current_branch

    step = record_forward_step(
        self,
        current_node_ids=multi_input_node_ids,
        current_branch=current_branch,
        head_commit=head_commit,
        diff_summary=diff_summary,
        commit_log=commit_log,
        extra_payloads=[],
        event_type="merge_created" if not join else "join_created",
        event_summary=(
            f"merge {merged_from_label} into {merged_into_label}"
            if not join
            else f"join {merged_from_label} into {merged_into_label}"
        ),
        event_data={
            "merged_from": merged_from_label,
            "merged_into": merged_into_label,
            "head_commit": head_commit,
            "join": join,
        },
        user_id=user_id,
        work_session_id=work_session_id,
        repo_id=repo_id,
    )

    if join:
        join_views = tuple(sorted({merged_into_label, merged_from_label}))
        typed_payload: MergePayload | JoinPayload = JoinPayload(
            payload_id=self._next_id("pl"),
            target_id=step.step_id,
            joined_views=join_views,
        )
    else:
        typed_payload = MergePayload(
            payload_id=self._next_id("pl"),
            target_id=step.step_id,
            merged_from=merged_from_label,
            merged_into=merged_into_label,
        )
    self.run_graph.attach_payload(typed_payload)

    return step
