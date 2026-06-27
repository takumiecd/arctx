"""arctx CLI revert command.

Drives a ``git revert`` and records the corresponding arctx Step with
BranchPayload, GitChangePayload, RevertPayload, BranchTipEvent, and
LanePointerEvent.
"""

from __future__ import annotations

import argparse
import json
import sys

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_lane_id_from_args,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``revert`` subcommand parser."""
    p = subparsers.add_parser(
        "revert",
        help="Revert a commit (or step) and record a arctx step",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sha", default=None, help="Commit sha to revert")
    g.add_argument("--step", default=None, help="Step id (lookup latest sha)")
    p.add_argument("-m", "--message", default=None, help="Override commit message")
    p.add_argument("--branch", default=None, help="Override branch name")
    p.add_argument("--run", default=None, help="Explicit run id")
    p.add_argument("--store-dir", default=None, help="Store directory")
    p.add_argument("--user", default=None, help="User id for attribution")
    p.add_argument("--lane", default=None, help="Work session id")
    return p


def run_revert_command(
    *,
    target_sha: str | None,
    target_step: str | None,
    message: str | None,
    branch: str | None,
    run_id: str | None,
    store_dir: str | None,
    user_id: str | None,
    lane_id: str | None,
) -> dict:
    """Execute a revert and persist the resulting graph records.

    Parameters
    ----------
    target_sha:
        Commit SHA to revert. Mutually exclusive with target_step.
    target_step:
        Step ID whose latest sha to revert.
    message:
        Override commit message.
    branch:
        Branch name override.
    run_id:
        Explicit run id.
    store_dir:
        Store directory.
    user_id:
        User id for work event attribution.
    lane_id:
        Work session id.

    Returns
    -------
    dict with step_id, output_node_id, branch, head_commit,
    reverted_step, reverted_commit.
    """
    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    before = graph_counts(handle)

    step = handle.git.revert(
        target_sha=target_sha,
        target_step=target_step,
        message=message,
        branch=branch,
        user_id=user_id,
        lane_id=lane_id,
    )

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane_id,
        before=before,
    )

    # Extract payload info for the result.
    git_payloads = handle.run_graph.payloads_for_step(
        step.step_id, payload_type="git_change"
    )
    head_commit = git_payloads[-1].head_commit if git_payloads else ""
    branch_payloads = handle.run_graph.payloads_for_step(
        step.step_id, payload_type="branch"
    )
    resolved_branch = branch_payloads[-1].branch if branch_payloads else ""
    revert_payloads = handle.run_graph.payloads_for_step(
        step.step_id, payload_type="revert"
    )
    reverted_step = revert_payloads[-1].reverted_step if revert_payloads else ""
    reverted_commit = revert_payloads[-1].reverted_commit if revert_payloads else ""

    return {
        "step_id": step.step_id,
        "output_node_id": step.output_node_id,
        "branch": resolved_branch,
        "head_commit": head_commit,
        "reverted_step": reverted_step,
        "reverted_commit": reverted_commit,
    }


def cli_revert(args) -> int:
    """Entry point for ``arctx revert`` subcommand."""
    from arctx.ext.git.verbs._forward_step import ParallelSessionConflict  # noqa: PLC0415

    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    lane_id = resolve_lane_id_from_args(args)

    try:
        result = run_revert_command(
            target_sha=args.sha,
            target_step=args.step,
            message=args.message,
            branch=args.branch,
            run_id=run_id,
            store_dir=args.store_dir,
            user_id=user_id,
            lane_id=lane_id,
        )
    except ParallelSessionConflict as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "hint: another session has advanced this branch. "
            "Rebase / pull before committing.",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0
