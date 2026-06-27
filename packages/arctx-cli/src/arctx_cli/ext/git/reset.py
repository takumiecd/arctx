"""arctx CLI reset command.

Resets the lane pointer to a past node WITHOUT creating a new Step.
Analogous to ``git reset``: moves HEAD back but does not produce a new commit.

For mode="hard", discarded steps receive a CutPayload. For "mixed" and
"soft" the steps are left active (working tree / index changes remain).
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
    """Register the ``reset`` subcommand parser."""
    p = subparsers.add_parser(
        "reset",
        help="Reset to a past node (no new step)",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--node", default=None, help="Target node id")
    g.add_argument(
        "--sha", default=None, help="Target commit sha (lookup via step_by_sha)"
    )
    p.add_argument(
        "--mode",
        choices=["hard", "mixed", "soft"],
        default="hard",
        help="Reset mode (default: hard)",
    )
    p.add_argument("--branch", default=None, help="Override branch name")
    p.add_argument("--run", default=None, help="Explicit run id")
    p.add_argument("--store-dir", default=None, help="Store directory")
    p.add_argument("--user", default=None, help="User id for attribution")
    p.add_argument("--lane", default=None, help="Work session id")
    return p


def run_reset_command(
    *,
    to_node_id: str | None,
    to_sha: str | None,
    mode: str,
    branch: str | None,
    run_id: str | None,
    store_dir: str | None,
    user_id: str | None,
    lane_id: str | None,
    dry_run: bool = False,
) -> dict:
    """Execute a reset and persist the resulting graph records.

    Parameters
    ----------
    to_node_id:
        Target node id. Mutually exclusive with to_sha.
    to_sha:
        Target commit sha (looked up via step_by_sha).
    mode:
        "hard" | "mixed" | "soft".
    branch:
        Branch name override for the LanePointerEvent.
    run_id:
        Explicit run id.
    store_dir:
        Store directory.
    user_id:
        User id for work event attribution.
    lane_id:
        Work session id.
    dry_run:
        If True, skip actual git operations.

    Returns
    -------
    dict with to_node_id, from_node_id, discarded_step_ids, mode,
    event_id.
    """
    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    before = graph_counts(handle)

    result = handle.git.reset(
        to_node_id=to_node_id,
        to_sha=to_sha,
        mode=mode,
        branch=branch,
        user_id=user_id,
        lane_id=lane_id,
        dry_run=dry_run,
    )

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane_id,
        before=before,
    )

    return result


def cli_reset(args) -> int:
    """Entry point for ``arctx reset`` subcommand."""
    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    lane_id = resolve_lane_id_from_args(args)

    try:
        result = run_reset_command(
            to_node_id=args.node,
            to_sha=args.sha,
            mode=args.mode,
            branch=args.branch,
            run_id=run_id,
            store_dir=args.store_dir,
            user_id=user_id,
            lane_id=lane_id,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0
