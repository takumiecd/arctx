"""arctx CLI merge command.

Drives a git merge (or arctx-only join) and records a multi-input Step
with MergePayload or JoinPayload.

Usage:
  arctx merge --other <ref> [-m <message>] [--join]
  arctx merge --other branch:<name> [--join]
  arctx merge --other node:<id> [--join]
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


def _parse_merge_ref(ref: str) -> tuple[str | None, str | None]:
    """Parse a merge ref into (other_branch, other_node_id).

    Formats accepted:
    - "branch:<name>"  → other_branch
    - "node:<id>"      → other_node_id
    - "<anything>"     → treated as branch name
    """
    if ref.startswith("branch:"):
        return ref[len("branch:"):], None
    if ref.startswith("node:"):
        return None, ref[len("node:"):]
    return ref, None


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``merge`` subcommand parser."""
    p = subparsers.add_parser(
        "merge",
        help="Drive a git merge and record a multi-input arctx step",
    )
    p.add_argument(
        "--other",
        required=True,
        metavar="REF",
        help=(
            "The branch or node to merge in. Format: 'branch:<name>', "
            "'node:<id>', or just '<name>' (auto-detected as branch name)."
        ),
    )
    p.add_argument(
        "-m",
        "--message",
        default=None,
        help="Override the merge commit message",
    )
    p.add_argument(
        "--branch",
        default=None,
        help="Override the current branch name (default: inferred from git)",
    )
    p.add_argument(
        "--join",
        action="store_true",
        help=(
            "Treat as a arctx-only join (no common ancestor). "
            "Records JoinPayload instead of MergePayload. "
            "Does NOT run git merge."
        ),
    )
    p.add_argument("--run", default=None, help="Explicit run id")
    p.add_argument("--store-dir", default=None, help="Store directory")
    p.add_argument("--user", default=None, help="User id for attribution")
    p.add_argument("--work-session", default=None, help="Work session id")
    return p


def run_merge_command(
    *,
    other: str,
    message: str | None,
    branch: str | None,
    run_id: str | None,
    store_dir: str | None,
    user_id: str | None,
    work_session_id: str | None,
    join: bool = False,
    # Test-only parameters; not exposed in the CLI parser.
    dry_run: bool = False,
    head_commit: str | None = None,
) -> dict:
    """Execute a merge (or join) and persist the resulting graph records.

    Parameters
    ----------
    other:
        Merge target reference. Format: 'branch:<name>', 'node:<id>', or '<name>'.
    message:
        Override the merge commit message. If None, git uses its default.
    branch:
        Current branch name override (None → infer from git).
    run_id:
        Explicit run id. If None, resolved from env / <gitdir>/arctx-id.
    store_dir:
        Store directory. If None, resolved from ARCTX_HOME.
    user_id:
        User id for work event attribution.
    work_session_id:
        Work session id.
    join:
        If True, use JoinPayload instead of MergePayload.

    Returns
    -------
    dict with step_id, output_node_id, branch, head_commit,
    input_node_ids, merge_payload_type.
    """
    other_branch, other_node_id = _parse_merge_ref(other)

    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    before = graph_counts(handle)

    step = handle.git.merge(
        other_branch=other_branch,
        other_node_id=other_node_id,
        message=message,
        branch=branch,
        user_id=user_id,
        work_session_id=work_session_id,
        join=join,
        dry_run=dry_run,
        head_commit=head_commit,
    )

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=work_session_id,
        before=before,
    )

    git_payloads = handle.run_graph.payloads_for_step(
        step.step_id, payload_type="git_change"
    )
    head_commit = git_payloads[-1].head_commit if git_payloads else ""
    branch_payloads = handle.run_graph.payloads_for_step(
        step.step_id, payload_type="branch"
    )
    resolved_branch = branch_payloads[-1].branch if branch_payloads else ""

    payload_type = "join" if join else "merge"

    return {
        "step_id": step.step_id,
        "output_node_id": step.output_node_id,
        "input_node_ids": list(step.input_node_ids),
        "branch": resolved_branch,
        "head_commit": head_commit,
        "merge_payload_type": payload_type,
    }


def cli_merge(args) -> int:
    """Entry point for ``arctx merge`` subcommand."""
    from arctx.ext.git.verbs._forward_step import ParallelSessionConflict  # noqa: PLC0415

    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    work_session_id = resolve_work_session_id_from_args(args)

    try:
        result = run_merge_command(
            other=args.other,
            message=args.message,
            branch=args.branch,
            run_id=run_id,
            store_dir=args.store_dir,
            user_id=user_id,
            work_session_id=work_session_id,
            join=args.join,
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
