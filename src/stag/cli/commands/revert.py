"""stag CLI revert command.

Drives a ``git revert`` and records the corresponding stag Transition with
BranchPayload, GitChangePayload, RevertPayload, BranchTipEvent, and
SessionPointerEvent.
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
    """Register the ``revert`` subcommand parser."""
    p = subparsers.add_parser(
        "revert",
        help="Revert a commit (or transition) and record a stag transition",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sha", default=None, help="Commit sha to revert")
    g.add_argument("--transition", default=None, help="Transition id (lookup latest sha)")
    p.add_argument("-m", "--message", default=None, help="Override commit message")
    p.add_argument("--branch", default=None, help="Override branch name")
    p.add_argument("--run", default=None, help="Explicit run id")
    p.add_argument("--store-dir", default=None, help="Store directory")
    p.add_argument("--user", default=None, help="User id for attribution")
    p.add_argument("--work-session", default=None, help="Work session id")
    return p


def run_revert_command(
    *,
    target_sha: str | None,
    target_transition: str | None,
    message: str | None,
    branch: str | None,
    run_id: str | None,
    store_dir: str | None,
    user_id: str | None,
    work_session_id: str | None,
) -> dict:
    """Execute a revert and persist the resulting graph records.

    Parameters
    ----------
    target_sha:
        Commit SHA to revert. Mutually exclusive with target_transition.
    target_transition:
        Transition ID whose latest sha to revert.
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
    work_session_id:
        Work session id.

    Returns
    -------
    dict with transition_id, output_node_id, branch, head_commit,
    reverted_transition, reverted_commit.
    """
    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    before = graph_counts(handle)

    transition = handle.revert(
        target_sha=target_sha,
        target_transition=target_transition,
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

    # Extract payload info for the result.
    git_payloads = handle.run_graph.payloads_for_transition(
        transition.transition_id, payload_type="git_change"
    )
    head_commit = git_payloads[-1].head_commit if git_payloads else ""
    branch_payloads = handle.run_graph.payloads_for_transition(
        transition.transition_id, payload_type="branch"
    )
    resolved_branch = branch_payloads[-1].branch if branch_payloads else ""
    revert_payloads = handle.run_graph.payloads_for_transition(
        transition.transition_id, payload_type="revert"
    )
    reverted_transition = revert_payloads[-1].reverted_transition if revert_payloads else ""
    reverted_commit = revert_payloads[-1].reverted_commit if revert_payloads else ""

    return {
        "transition_id": transition.transition_id,
        "output_node_id": transition.output_node_id,
        "branch": resolved_branch,
        "head_commit": head_commit,
        "reverted_transition": reverted_transition,
        "reverted_commit": reverted_commit,
    }


def cli_revert(args) -> int:
    """Entry point for ``stag revert`` subcommand."""
    from stag.core.run._forward_transition import ParallelSessionConflict  # noqa: PLC0415

    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    work_session_id = resolve_work_session_id_from_args(args)

    try:
        result = run_revert_command(
            target_sha=args.sha,
            target_transition=args.transition,
            message=args.message,
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
