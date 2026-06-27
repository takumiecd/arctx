"""arctx CLI guide command."""

import argparse

def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "guide",
        help="Print the arctx usage guide and current context for AI agents",
    )
    parser.add_argument("--run", default=None, help="Specific run ID")
    parser.add_argument("--store-dir", default=None, help="Specific store directory")
    return parser


def cli_guide(args) -> int:
    guide_text = """\
# arctx System Guide for AI Agents

`arctx` is a tool for recording optimization and problem-solving processes.
You are currently operating in a workspace that uses `arctx`.

## Core Concepts
* **Node & Step**: The Directed Acyclic Graph (DAG) that records history. `Node` = state, `Step` = transition.
* **Payload**: Domain-specific data attached to Nodes/Steps.
* **Lane**: A workspace/branch that isolates problem-solving steps.

## Essential Commands

As an AI agent (Codex, Claude Code, agy, etc.), use these commands to understand the context and record your work:

* `arctx dump --format outline` : View the entire history graph.
* `arctx dump --format outline --lane` : View the history of the current lane.
* `arctx lane` : Show the currently active lane.
* `arctx show <ID>` : Show details of a specific Node, Step, or Payload.
* `arctx lane join <LANE> --summary "..."` : Merge frontier nodes in a lane and attach a summary.
* `arctx git commit` : Record a git commit as a step in the arctx graph.
* `arctx git verify` : Run verification scripts and attach results to the graph.
"""
    # Try to load execution context dynamically
    try:
        from arctx_cli.context import resolve_run_id_from_args, resolve_store
        run_id = resolve_run_id_from_args(args)
        store = resolve_store(args.store_dir)
        if store.run_path(run_id).exists():
            handle = store.load_run(run_id)
            guide_text += f"\n## Current Context\n\n* **Run ID**: `{run_id}`\n"
            
            from arctx_cli.paths import find_repo_root, read_arctx_lane
            try:
                repo_root = find_repo_root()
                lane_name = read_arctx_lane(repo_root)
                guide_text += f"* **Current Lane**: `{lane_name}`\n"
                
                lane_obj = None
                for lane in handle.run_graph.lanes.values():
                    if lane.name == lane_name:
                        lane_obj = lane
                        break
                
                if lane_obj:
                    from arctx.core.lanes import lane_membership
                    from arctx.core.cuts import is_active_node
                    membership = lane_membership(handle.run_graph)
                    group = next((g for g in membership.groups if g.lane_id == lane_obj.lane_id), None)
                    if group:
                        frontiers = []
                        for nid in group.node_ids:
                            if is_active_node(handle.run_graph, nid) and not handle.run_graph.steps_from_node(nid):
                                frontiers.append(nid)
                        
                        if frontiers:
                            guide_text += "* **Active Frontiers in Lane**:\n"
                            for f in frontiers:
                                payloads = handle.run_graph.payloads_for_node(f)
                                types = [p.payload_type for p in payloads]
                                type_str = f" ({', '.join(types)})" if types else ""
                                guide_text += f"  - `{f}`{type_str}\n"
                        else:
                            guide_text += "* **Active Frontiers in Lane**: (none)\n"
            except Exception:
                guide_text += "* **Current Lane**: (not set or outside git repo)\n"
    except Exception as e:
        # Silently degrade if context cannot be loaded
        pass

    print(guide_text)
    return 0
