"""arctx CLI commit command.

Drives a git commit and records the corresponding arctx Step with
BranchPayload, GitChangePayload, BranchTipEvent, and LanePointerEvent.
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
    """Register the ``commit`` subcommand parser."""
    p = subparsers.add_parser(
        "commit",
        help="Drive a git commit and record a arctx step",
    )
    p.add_argument("-m", "--message", required=True, help="Commit message")
    p.add_argument(
        "--from",
        dest="from_nodes",
        action="append",
        default=None,
        metavar="NODE",
        help=(
            "Branch this commit off the given node instead of the session / "
            "branch tip. Repeat for a fan-in. This is how sibling experiments "
            "fan out from a shared baseline node."
        ),
    )
    p.add_argument(
        "--branch",
        default=None,
        help="Override branch name (default: current git branch)",
    )
    p.add_argument(
        "--merge",
        default=None,
        metavar="REF",
        help=(
            "Merge target. Format: 'branch:<name>', 'node:<id>', or just '<name>' "
            "(auto-detected as branch name). Drives git merge and records a "
            "multi-input step with MergePayload."
        ),
    )
    p.add_argument("--run", default=None, help="Explicit run id")
    p.add_argument("--store-dir", default=None, help="Store directory")
    p.add_argument("--user", default=None, help="User id for attribution")
    p.add_argument("--lane", default=None, help="Work session id")
    return p


def _parse_merge_ref(ref: str) -> tuple[str | None, str | None]:
    """Parse a merge ref string into (other_branch, other_node_id).

    Formats accepted:
    - "branch:<name>"  → branch name
    - "node:<id>"      → node id
    - "<anything>"     → treated as branch name (auto-detect)
    """
    if ref.startswith("branch:"):
        return ref[len("branch:"):], None
    if ref.startswith("node:"):
        return None, ref[len("node:"):]
    # Auto-detect: treat as branch name.
    return ref, None


def run_commit_command(
    *,
    message: str,
    branch: str | None,
    run_id: str | None,
    store_dir: str | None,
    user_id: str | None,
    lane_id: str | None,
    merge: str | None = None,
    from_node_ids: tuple[str, ...] | None = None,
    # Test-only parameters; not exposed in the CLI parser.
    dry_run: bool = False,
    head_commit: str | None = None,
) -> dict:
    """Execute a commit (or merge) and persist the resulting graph records.

    Parameters
    ----------
    message:
        Git commit message.
    branch:
        Branch name override (None → infer from git).
    run_id:
        Explicit run id. If None, resolved from env / <gitdir>/arctx-id.
    store_dir:
        Store directory. If None, resolved from ARCTX_HOME.
    user_id:
        User id for work event attribution.
    lane_id:
        Work session id.
    merge:
        If set, drive a merge instead of a plain commit. Format:
        'branch:<name>', 'node:<id>', or '<name>' (branch auto-detect).

    Returns
    -------
    dict with step_id, output_node_id, branch, head_commit.
    """
    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    before = graph_counts(handle)

    if merge is not None:
        other_branch, other_node_id = _parse_merge_ref(merge)
        step = handle.git.merge(
            other_branch=other_branch,
            other_node_id=other_node_id,
            message=message,
            branch=branch,
            user_id=user_id,
            lane_id=lane_id,
            dry_run=dry_run,
            head_commit=head_commit,
        )
    else:
        step = handle.git.commit(
            message=message,
            branch=branch,
            user_id=user_id,
            lane_id=lane_id,
            from_node_ids=from_node_ids,
            dry_run=dry_run,
            head_commit=head_commit,
        )

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane_id,
        before=before,
    )

    # Extract GitChangePayload info for the result.
    git_payloads = handle.run_graph.payloads_for_step(
        step.step_id, payload_type="git_change"
    )
    head_commit = git_payloads[-1].head_commit if git_payloads else ""
    branch_payloads = handle.run_graph.payloads_for_step(
        step.step_id, payload_type="branch"
    )
    resolved_branch = branch_payloads[-1].branch if branch_payloads else ""

    result: dict = {
        "step_id": step.step_id,
        "output_node_id": step.output_node_id,
        "branch": resolved_branch,
        "head_commit": head_commit,
    }
    if merge is not None:
        result["merge"] = merge
    return result


def cli_commit(args) -> int:
    """Entry point for ``arctx commit`` subcommand."""
    from arctx.ext.git.verbs._forward_step import ParallelSessionConflict  # noqa: PLC0415

    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    lane_id = resolve_lane_id_from_args(args)

    from_nodes = getattr(args, "from_nodes", None)
    merge = getattr(args, "merge", None)
    if from_nodes and merge is not None:
        print("error: --from cannot be combined with --merge", file=sys.stderr)
        return 1

    try:
        result = run_commit_command(
            message=args.message,
            branch=args.branch,
            run_id=run_id,
            store_dir=args.store_dir,
            user_id=user_id,
            lane_id=lane_id,
            merge=merge,
            from_node_ids=tuple(from_nodes) if from_nodes else None,
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
