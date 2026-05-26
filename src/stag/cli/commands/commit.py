"""stag CLI commit command.

Drives a git commit and records the corresponding stag Transition with
BranchPayload, GitChangePayload, BranchTipEvent, and SessionPointerEvent.
"""

from __future__ import annotations

import argparse
import json
import sys

from stag.cli.append_batch import graph_counts, maybe_append_or_save
from stag.cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``commit`` subcommand parser."""
    p = subparsers.add_parser(
        "commit",
        help="Drive a git commit and record a stag transition",
    )
    p.add_argument("-m", "--message", required=True, help="Commit message")
    p.add_argument(
        "--branch",
        default=None,
        help="Override branch name (default: current git branch)",
    )
    p.add_argument("--run", default=None, help="Explicit run id")
    p.add_argument("--store-dir", default=None, help="Store directory")
    p.add_argument("--user", default=None, help="User id for attribution")
    p.add_argument("--work-session", default=None, help="Work session id")
    return p


def run_commit_command(
    *,
    message: str,
    branch: str | None,
    run_id: str | None,
    store_dir: str | None,
    user_id: str | None,
    work_session_id: str | None,
) -> dict:
    """Execute a commit and persist the resulting graph records.

    Parameters
    ----------
    message:
        Git commit message.
    branch:
        Branch name override (None → infer from git).
    run_id:
        Explicit run id. If None, resolved from env / .stag-id.
    store_dir:
        Store directory. If None, resolved from STAG_HOME.
    user_id:
        User id for work event attribution.
    work_session_id:
        Work session id.

    Returns
    -------
    dict with transition_id, output_node_id, branch, head_commit.
    """
    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    before = graph_counts(handle)

    transition = handle.commit(
        message=message,
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

    # Extract GitChangePayload info for the result.
    git_payloads = handle.run_graph.payloads_for_transition(
        transition.transition_id, payload_type="git_change"
    )
    head_commit = git_payloads[-1].head_commit if git_payloads else ""
    branch_payloads = handle.run_graph.payloads_for_transition(
        transition.transition_id, payload_type="branch"
    )
    resolved_branch = branch_payloads[-1].branch if branch_payloads else ""

    return {
        "transition_id": transition.transition_id,
        "output_node_id": transition.output_node_id,
        "branch": resolved_branch,
        "head_commit": head_commit,
    }


def cli_commit(args) -> int:
    """Entry point for ``stag commit`` subcommand."""
    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    work_session_id = resolve_work_session_id_from_args(args)

    try:
        result = run_commit_command(
            message=args.message,
            branch=args.branch,
            run_id=run_id,
            store_dir=args.store_dir,
            user_id=user_id,
            work_session_id=work_session_id,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0
