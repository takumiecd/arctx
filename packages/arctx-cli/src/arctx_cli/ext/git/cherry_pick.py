"""arctx CLI cherry-pick command.

Drives a ``git cherry-pick`` and records the corresponding arctx Step with
BranchPayload, GitChangePayload, CherryPickPayload, BranchTipEvent, and
SessionPointerEvent.
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
    resolve_work_session_id_from_args,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``cherry-pick`` subcommand parser."""
    p = subparsers.add_parser(
        "cherry-pick",
        help="Cherry-pick a commit and record a arctx step",
    )
    p.add_argument("--sha", required=True, help="Commit sha to cherry-pick")
    p.add_argument("--branch", default=None, help="Override branch name")
    p.add_argument("--run", default=None, help="Explicit run id")
    p.add_argument("--store-dir", default=None, help="Store directory")
    p.add_argument("--user", default=None, help="User id for attribution")
    p.add_argument("--work-session", default=None, help="Work session id")
    return p


def run_cherry_pick_command(
    *,
    source_sha: str,
    branch: str | None,
    run_id: str | None,
    store_dir: str | None,
    user_id: str | None,
    work_session_id: str | None,
) -> dict:
    """Execute a cherry-pick and persist the resulting graph records.

    Parameters
    ----------
    source_sha:
        Commit SHA to cherry-pick.
    branch:
        Branch name override.
    run_id:
        Explicit run id.
    store_dir:
        Store directory.
    user_id:
        User id for work event attribution.
    work_session_id:
        Work session id.

    Returns
    -------
    dict with step_id, output_node_id, branch, head_commit,
    source_step, source_commit.
    """
    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    before = graph_counts(handle)

    step = handle.git.cherry_pick(
        source_sha=source_sha,
        branch=branch,
        user_id=user_id,
        work_session_id=work_session_id,
    )

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=work_session_id,
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
    cp_payloads = handle.run_graph.payloads_for_step(
        step.step_id, payload_type="cherry_pick"
    )
    source_step = cp_payloads[-1].source_step if cp_payloads else None
    source_commit = cp_payloads[-1].source_commit if cp_payloads else ""

    return {
        "step_id": step.step_id,
        "output_node_id": step.output_node_id,
        "branch": resolved_branch,
        "head_commit": head_commit,
        "source_step": source_step,
        "source_commit": source_commit,
    }


def cli_cherry_pick(args) -> int:
    """Entry point for ``arctx cherry-pick`` subcommand."""
    from arctx.ext.git.verbs._forward_step import ParallelSessionConflict  # noqa: PLC0415

    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    work_session_id = resolve_work_session_id_from_args(args)

    try:
        result = run_cherry_pick_command(
            source_sha=args.sha,
            branch=args.branch,
            run_id=run_id,
            store_dir=args.store_dir,
            user_id=user_id,
            work_session_id=work_session_id,
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
