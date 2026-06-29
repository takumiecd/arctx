"""arctx CLI guide command."""

import argparse

def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "guide",
        help="Print the arctx usage guide and current context",
    )
    parser.add_argument("--run", default=None, help="Specific run ID")
    parser.add_argument("--store-dir", default=None, help="Specific store directory")
    return parser


def cli_guide(args) -> int:
    guide_text = """\
# arctx Guide

`arctx` is a tool for recording optimization and problem-solving processes.

## Core Concepts
* **Node & Step**: The Directed Acyclic Graph (DAG) that records history. `Node` = state, `Step` = transition.
* **Payload**: Domain-specific data attached to Nodes/Steps.
* **Lane**: A workspace/branch that isolates problem-solving steps.

## Recommended Workflow
1. **Understand Context**: Use `arctx dump` to view the graph. Check your **Current Lane** and **Active Frontiers** at the bottom of this guide to know where to resume work.
2. **Isolate Approaches**: Use lanes to explore different solutions independently.
3. **Record Everything**: Record progress with `arctx add --from NODE ...` or `arctx git commit`. `arctx add` creates a Step and its output Node; nodes are not created standalone.
4. **Close & Summarize**: When a lane's work is done, close it with `arctx lane close NAME --summary "..."`. This is the *close* action — use it even for a single linear chain, not only when several paths must be merged. The summary is required and becomes the closing node's payload, so **put your full synthesis there** (one leaf → it stamps that leaf; several leaves → it merges them into one node). Use `--summary-format markdown|html|text` when Markdown is not the best fit. Do **not** write a separate synthesis step and then close on top of it — the close *is* your synthesis-and-close. A closed lane refuses further writes; reopen it with `arctx lane open NAME` to resume.

## Parallel Experiment Strategy

When approaches are independent, fan them out from the same baseline Node instead of serializing them in one lane. Give each approach its own lane, and for code changes prefer a separate git worktree as well. This is different from ordinary git branching: ARCTX is recording the experiment relationship in the RunGraph, not just moving code refs.

Record each branch's hypothesis, result, and evaluation signal. Do not discard a branch only because it is weak by itself; sometimes the best answer is a later multi-input join of ideas that were mediocre in isolation. After independent runs finish, combine promising terminal Nodes with repeated `--from` arguments and record the synthesis as one Step. Use `cut` for branches that should remain in history but no longer participate in the active solution.

## Essential Core Commands

* `arctx dump --format outline` : View the entire history graph.
* `arctx dump --format outline --lane` : View the history of the current lane.
* `arctx add --from <NODE> --type <TYPE> --field key=value` : Add a Step from one or more input Nodes and create its output Node. Repeat `--from` for a multi-input join.
* `arctx attach <NODE_OR_STEP> --type <TYPE> --field key=value` : Attach a generic payload. Use `--payload-type summary` for typed summary payloads.
* `arctx lane` : Show the currently active lane.
* `arctx show <ID>` : Show details of a specific Node, Step, or Payload.
* `arctx lane close <LANE> --summary "<your synthesis>" [--summary-format markdown|html|text]` : Close a lane. Attaches the required summary to its terminal (its one leaf, or a fresh node merging several leaves) and marks it closed; writes are then refused until reopened. Put your findings in `--summary` here — not in a separate preceding step. (`arctx lane join` is a deprecated alias.)
* `arctx lane open <LANE>` : Reopen a closed lane to resume work.
"""
    # Try to load execution context dynamically
    try:
        from arctx_cli.context import resolve_run_id_from_args, resolve_store
        run_id = resolve_run_id_from_args(args)
        store = resolve_store(args.store_dir)
        run_dir = None
        if run_id:
            candidate = store.run_path(run_id)
            if candidate.exists():
                run_dir = str(candidate)

        # Load Extensions Guide
        ext_guide_text = ""
        available_exts_text = ""
        if run_dir:
            from arctx.ext.enabled import load_enabled
            from arctx.ext import load_extension, list_available
            enabled_exts = load_enabled(run_dir)
            enabled_names = {ee.name for ee in enabled_exts}
            all_available = list_available()

            for name in enabled_names:
                try:
                    ext = load_extension(name)
                    ext_text = ext.guide_text()
                    if ext_text:
                        ext_guide_text += f"\n### {ext.name.capitalize()} Extension\n{ext_text}\n"
                except Exception:
                    pass

            for name in all_available:
                if name not in enabled_names:
                    try:
                        ext = load_extension(name)
                        desc = ext.description or "(No description available)"
                        available_exts_text += f"* `{name}` : {desc}\n"
                    except Exception:
                        pass

        guide_text += "\n## Managing Extensions\n"
        guide_text += "Extensions add domain-specific workflows (e.g. `git`, `diagram`) to arctx.\n"
        guide_text += "* List available extensions: `arctx ext list`\n"
        guide_text += "* Enable an extension: `arctx ext enable <name>`\n"
        guide_text += "* Disable an extension: `arctx ext disable <name>`\n"

        if available_exts_text:
            guide_text += f"\n### Available Extensions (Not Enabled)\n{available_exts_text}"

        if ext_guide_text:
            guide_text += f"\n## Enabled Extensions Commands\n{ext_guide_text}"

        # Current Context
        if run_dir:
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
