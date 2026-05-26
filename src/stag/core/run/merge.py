"""RunHandle.merge implementation.

Drives a git merge (or records a stag-only join) and records a multi-input
Transition with MergePayload or JoinPayload.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from stag.core.schema.graph import Transition
from stag.core.schema.payloads import JoinPayload, MergePayload
from stag.core.run._forward_transition import (
    capture_git_info,
    check_branch_tip_consistency,
    record_forward_transition,
    resolve_current_branch,
    resolve_current_node_ids,
)
from stag.core.schema.work_helpers import latest_branch_tip

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stag.core.run.handle import RunHandle


def _resolve_other_node_id(
    self: "RunHandle",
    *,
    other_node_id: str | None,
    other_branch: str | None,
    work_session_id: str | None,
) -> str:
    """Resolve the 'other' tip node to merge from.

    Priority:
    1. Explicit other_node_id.
    2. Latest BranchTipEvent for other_branch.
    3. Latest SessionPointerEvent for other_branch (fallback — looks up by branch name).

    Raises
    ------
    ValueError
        If neither other_node_id nor other_branch is given, or if the branch
        tip cannot be resolved.
    """
    if other_node_id is not None:
        return other_node_id

    if other_branch is None:
        raise ValueError(
            "merge_impl requires either other_node_id or other_branch"
        )

    tip_event = latest_branch_tip(self.run_graph, other_branch)
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
) -> Transition:
    """Drive ``git merge <other>`` and record a multi-input Transition.

    Steps (per REDESIGN §10.4):
    1. Resolve current_node_ids from the latest SessionPointerEvent (or root).
    2. Resolve other_node_id from argument or via latest BranchTipEvent.
    3. Run ``git merge <other_branch_or_sha>`` (unless dry_run).
    4. Append:
       - new Transition(input_node_ids=(current_node, other_node), output=new node)
       - BranchPayload(current_branch)
       - GitChangePayload(merge commit sha)
       - MergePayload(merged_from, merged_into)  when join=False
         or JoinPayload(joined_views)            when join=True
       - BranchTipEvent(current_branch, new node)
       - SessionPointerEvent(current=(new node,), current_branch)
    5. Return the new Transition.

    Parameters
    ----------
    other_node_id:
        Node ID of the other branch tip to merge in. Either this or
        other_branch must be provided.
    other_branch:
        Name of the other git branch. Used to look up the tip node via the
        latest BranchTipEvent, and passed to ``git merge`` if not dry_run.
        Either this or other_node_id must be provided.
    message:
        Override the merge commit message. If None, git uses its default.
    branch:
        Override the current branch name. If None, inferred from git.
    repo_path:
        Path to the git repo root. Defaults to cwd.
    user_id:
        User ID for attribution. If None, work events are not recorded.
    work_session_id:
        Work session ID. If None, work events are not recorded.
    head_commit:
        Override the HEAD commit SHA (for testing / dry-run). If None
        and dry_run is False, git is queried for the HEAD SHA after merge.
    dry_run:
        If True, skip the actual ``git merge`` call. Useful for testing
        without a real git repository.
    join:
        If True, record a JoinPayload (stag-only join, no common ancestor)
        instead of a MergePayload.

    Returns
    -------
    The newly created Transition.
    """
    resolved_repo_path: Path = repo_path or Path.cwd()

    # ------------------------------------------------------------------
    # 1. Resolve current_node_ids (the "into" side).
    # ------------------------------------------------------------------
    current_node_ids = resolve_current_node_ids(self, work_session_id)

    for nid in current_node_ids:
        self._ensure_active_node(nid)

    # ------------------------------------------------------------------
    # 2. Resolve other_node_id (the "from" side).
    # ------------------------------------------------------------------
    resolved_other_node_id = _resolve_other_node_id(
        self,
        other_node_id=other_node_id,
        other_branch=other_branch,
        work_session_id=work_session_id,
    )
    self._ensure_active_node(resolved_other_node_id)

    # Build the full input set: current tip(s) + other tip.
    # Deduplicate while preserving order.
    seen: set[str] = set()
    merged_inputs: list[str] = []
    for nid in (*current_node_ids, resolved_other_node_id):
        if nid not in seen:
            seen.add(nid)
            merged_inputs.append(nid)
    multi_input_node_ids = tuple(merged_inputs)

    # ------------------------------------------------------------------
    # 2b. Resolve current_branch (the "into" branch).
    # ------------------------------------------------------------------
    current_branch = resolve_current_branch(
        branch=branch,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    # ------------------------------------------------------------------
    # 2c. Parallel-session guard (§7.2).
    # Only enforced when a work session is tracked.
    # ------------------------------------------------------------------
    if work_session_id is not None:
        check_branch_tip_consistency(self.run_graph, current_branch, current_node_ids)

    # ------------------------------------------------------------------
    # 3. Run git merge (unless dry_run).
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 4. Capture git info.
    # ------------------------------------------------------------------
    if head_commit is None:
        if dry_run:
            head_commit = "dry_run_merge_sha_" + self._next_id("sha")
        else:
            from stag.core.git import repo as git_repo  # noqa: PLC0415
            head_commit = git_repo.current_commit(resolved_repo_path)

    diff_summary, commit_log = capture_git_info(
        head_commit=head_commit,
        dry_run=dry_run,
        repo_path=resolved_repo_path,
    )

    # ------------------------------------------------------------------
    # 5. Build extra payload (MergePayload or JoinPayload).
    # ------------------------------------------------------------------
    # target_id will be set to the new transition_id inside
    # record_forward_transition; we use a placeholder here and replace below.
    # However, record_forward_transition attaches extra_payloads as-is, so we
    # need to build a two-step approach: record the transition first, then
    # attach the typed merge/join payload.
    #
    # To keep things simple we collect the payloads _after_ we know the
    # transition_id by calling record_forward_transition and then attaching.

    # We piggy-back on record_forward_transition for standard payloads.
    # For the merge/join payload we build it after knowing the transition_id.

    # Compute labels for the merge/join payload.
    merged_from_label = other_branch or resolved_other_node_id
    merged_into_label = current_branch

    # We cannot inject the merge-specific payload as an "extra" because
    # record_forward_transition requires target_id to be pre-set. Instead,
    # we call record_forward_transition with empty extra_payloads and attach
    # afterwards.
    transition = record_forward_transition(
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
    )

    # Attach MergePayload or JoinPayload to the new transition.
    if join:
        join_views = tuple(sorted({merged_into_label, merged_from_label}))
        typed_payload: MergePayload | JoinPayload = JoinPayload(
            payload_id=self._next_id("pl"),
            target_id=transition.transition_id,
            joined_views=join_views,
        )
    else:
        typed_payload = MergePayload(
            payload_id=self._next_id("pl"),
            target_id=transition.transition_id,
            merged_from=merged_from_label,
            merged_into=merged_into_label,
        )
    self.run_graph.attach_payload(typed_payload)

    return transition
