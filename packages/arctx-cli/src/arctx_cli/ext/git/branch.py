"""arctx CLI branch command.

Provides:
  arctx branch list       — list all known branches and their tip node IDs
  arctx branch show NAME  — show tip, members count, and BranchPayload steps
"""

from __future__ import annotations

import argparse
import json
import sys

from arctx_cli.context import resolve_run_id_from_args, resolve_store
from arctx.core.schema.work_helpers import BRANCH_TIP_EVENT
from arctx.ext.git.queries import branch_members


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``branch`` subcommand parser."""
    p = subparsers.add_parser("branch", help="Inspect git branches recorded in arctx")
    branch_sub = p.add_subparsers(dest="branch_command", required=True)

    sp_list = branch_sub.add_parser("list", help="List all known branches")
    sp_list.add_argument("--run", default=None)
    sp_list.add_argument("--store-dir", default=None)

    sp_show = branch_sub.add_parser("show", help="Show branch tip and members")
    sp_show.add_argument("name", help="Branch name")
    sp_show.add_argument("--run", default=None)
    sp_show.add_argument("--store-dir", default=None)

    return p


def _all_branches(graph) -> dict[str, str]:
    """Return a mapping of branch_name → tip_node_id from BranchTipEvents.

    The latest event per branch wins (events are in append order).
    """
    tips: dict[str, str] = {}
    for event in graph.work_events:
        if event.event_type == BRANCH_TIP_EVENT:
            branch = str(event.data.get("branch", ""))
            tip = str(event.data.get("tip_node_id", ""))
            if branch:
                tips[branch] = tip
    return tips


def run_branch_list_command(*, run_id: str | None, store_dir: str | None) -> list[dict]:
    """Return a list of all branches with their current tip node IDs.

    Returns
    -------
    List of dicts with keys ``branch`` and ``tip_node_id``.
    """
    store = resolve_store(store_dir)
    handle = store.load_run(run_id)
    branches = _all_branches(handle.run_graph)
    return [{"branch": b, "tip_node_id": t} for b, t in sorted(branches.items())]


def run_branch_show_command(
    *, name: str, run_id: str | None, store_dir: str | None
) -> dict:
    """Return detailed info for a single branch.

    Returns
    -------
    dict with keys:
      - branch: str
      - tip_node_id: str | None
      - members_count: int
      - members_sample: list[str] (up to 10 node IDs)
      - steps: list[dict] for steps that carry a BranchPayload
        targeting this branch
    """
    store = resolve_store(store_dir)
    handle = store.load_run(run_id)
    graph = handle.run_graph

    branches = _all_branches(graph)
    tip_node_id: str | None = branches.get(name)

    members: set[str] = set()
    if tip_node_id:
        members = branch_members(graph, name)

    # Find steps with BranchPayload(branch=name).
    branch_steps = []
    for t_id, step in graph.steps.items():
        for p in graph.payloads_for_step(t_id, payload_type="branch"):
            if getattr(p, "branch", None) == name:
                # Collect associated GitChangePayload info.
                git_payloads = graph.payloads_for_step(t_id, payload_type="git_change")
                head_commit = git_payloads[-1].head_commit if git_payloads else None
                branch_steps.append(
                    {
                        "step_id": t_id,
                        "output_node_id": step.output_node_id,
                        "head_commit": head_commit,
                        "branch_payload_id": p.payload_id,
                    }
                )

    return {
        "branch": name,
        "tip_node_id": tip_node_id,
        "members_count": len(members),
        "members_sample": sorted(members)[:10],
        "steps": branch_steps,
    }


def cli_branch(args) -> int:
    """Entry point for ``arctx branch`` subcommand."""
    run_id = resolve_run_id_from_args(args)

    if args.branch_command == "list":
        try:
            result = run_branch_list_command(run_id=run_id, store_dir=args.store_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 0

    if args.branch_command == "show":
        try:
            result = run_branch_show_command(
                name=args.name, run_id=run_id, store_dir=args.store_dir
            )
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 0

    return 1
