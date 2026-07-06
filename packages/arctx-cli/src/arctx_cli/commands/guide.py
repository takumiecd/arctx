"""arctx CLI guide command."""

import argparse

from arctx_cli.commands._lane_context import (
    describe_frontier_candidates,
    resolve_lane_frontiers,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "guide",
        help="Print the arctx usage guide and current context",
    )
    parser.add_argument("--run", default=None, help="Specific run ID")
    parser.add_argument("--store-dir", default=None, help="Specific store directory")
    parser.add_argument("--lane", default=None, help="Specific lane (id or name)")
    parser.add_argument(
        "--context",
        action="store_true",
        help=(
            "Skip the static guide text; print only the dynamic context "
            "(Run ID, Current Lane, Active Frontiers, enabled extensions). "
            "Cheap enough to call at the start of every agent turn."
        ),
    )
    return parser


STATIC_GUIDE_TEXT = """\
# arctx Guide

`arctx` is a tool for recording optimization and problem-solving processes.

## Core Concepts
* **Node & Step**: The Directed Acyclic Graph (DAG) that records history. `Node` = state, `Step` = transition.
* **Payload**: Domain-specific data attached to Nodes/Steps.
* **Lane**: A workspace/branch that isolates problem-solving steps.

## Recommended Workflow
1. **Understand Context**: Use `arctx log` for a chronological read of the run (oldest first, like `git log --oneline`; add `--lanes` for a phase-level table of contents), `arctx dump` to view the graph structure, or `arctx guide --context` for a cheap dynamic-only snapshot. Check your **Current Lane** and **Active Frontiers** at the bottom of this guide to know where to resume work.
2. **Isolate Approaches**: Use lanes to explore different solutions independently.
3. **Record Everything**: Record progress with `arctx add --from NODE ...` or `arctx git commit`. `arctx add` creates a Step and its output Node; nodes are not created standalone. `--from` is optional: if omitted, it defaults to the current lane's single active frontier node. On a fresh run with zero frontiers, it falls back to the run root as long as the root hasn't been used yet (so the very first `add` needs no `--from`). Otherwise, zero or several frontiers errors with a corrective message.
4. **Close & Summarize**: When a lane's work is done, close it with `arctx lane close NAME --summary "..."`. This is the *close* action — use it even for a single linear chain, not only when several paths must be merged. The summary is required and becomes the closing node's payload, so **put your full synthesis there** (one leaf → it stamps that leaf; several leaves → it merges them into one node). Use `--summary-format markdown|html|text` when Markdown is not the best fit. Do **not** write a separate synthesis step and then close on top of it — the close *is* your synthesis-and-close. A closed lane refuses further writes; reopen it with `arctx lane open NAME` to resume.

## Parallel Experiment Strategy

When approaches are independent, fan them out from the same baseline Node instead of serializing them in one lane. Give each approach its own lane, and for code changes prefer a separate git worktree as well. This is different from ordinary git branching: ARCTX is recording the experiment relationship in the RunGraph, not just moving code refs.

Record each branch's hypothesis, result, and evaluation signal. Do not discard a branch only because it is weak by itself; sometimes the best answer is a later multi-input join of ideas that were mediocre in isolation. After independent runs finish, combine promising terminal Nodes with repeated `--from` arguments and record the synthesis as one Step. Use `cut` for branches that should remain in history but no longer participate in the active solution.

## Essential Core Commands

* `arctx log` : Chronological, oldest-first listing of the run (`git log --oneline` style), built from work events.
* `arctx log --lanes` : Phase-level table of contents — one line per lane, ordered by when it started.
* `arctx dump --format outline` : View the entire history graph.
* `arctx dump --format outline --lane` : View the history of the current lane.
* `arctx guide --context` : Print only the dynamic context (Run ID / Current Lane / Active Frontiers / enabled extensions) — cheap to call every turn.
* `arctx add --from <NODE> --type <TYPE> --field key=value` : Add a Step from one or more input Nodes and create its output Node. Repeat `--from` for a multi-input join. Omit `--from` to default to the current lane's single active frontier node.
* `arctx attach <NODE_OR_STEP> --type <TYPE> --field key=value` : Attach a generic payload. Use `--payload-type summary` for typed summary payloads.
* `arctx lane` : Show the currently active lane.
* `arctx show <ID>` : Show details of a specific Node, Step, or Payload.
* `arctx lane close <LANE> --summary "<your synthesis>" [--summary-format markdown|html|text]` : Close a lane. Attaches the required summary to its terminal (its one leaf, or a fresh node merging several leaves) and marks it closed; writes are then refused until reopened. Put your findings in `--summary` here — not in a separate preceding step. (`arctx lane join` is a deprecated alias.)
* `arctx lane open <LANE>` : Reopen a closed lane to resume work.
"""


def _extensions_text(run_dir):
    """Return (enabled_names, ext_guide_text, available_exts_text) for a run_dir."""
    from arctx.ext.enabled import load_enabled
    from arctx.ext import load_extension, list_available

    ext_guide_text = ""
    available_exts_text = ""
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

    return enabled_names, ext_guide_text, available_exts_text


def build_current_context(args) -> str:
    """Build the "## Current Context" block: Run ID / Current Lane / Active
    Frontiers / enabled extension names.

    This is the single source of dynamic context, shared by the full guide
    (``arctx guide``) and the dynamic-only mode (``arctx guide --context``) so
    the two never drift. Never raises: any failure to resolve context is
    folded into a visible ``(context unavailable: ...)`` note instead of being
    silently swallowed, so an agent can tell when context is missing.
    """
    from arctx_cli.context import (
        resolve_run_id_from_args,
        resolve_store,
        resolve_lane_id_from_args,
    )

    text = "\n## Current Context\n\n"
    try:
        run_id = resolve_run_id_from_args(args)
        store = resolve_store(args.store_dir)
        run_dir = None
        if run_id:
            candidate = store.run_path(run_id)
            if candidate.exists():
                run_dir = str(candidate)

        if not run_dir:
            text += f"(context unavailable: no run found for {run_id!r})\n"
            return text

        text += f"* **Run ID**: `{run_id}`\n"

        handle = store.load_run(run_id)
        lane_id = resolve_lane_id_from_args(args)
        context = resolve_lane_frontiers(handle, lane_id)
        lane_label = context.lane_name or context.lane_id
        text += f"* **Current Lane**: `{lane_label}`\n"

        frontiers = context.frontier_node_ids
        if frontiers:
            text += "* **Active Frontiers in Lane**:\n"
            for line in describe_frontier_candidates(handle, frontiers):
                text += f"  - `{line}`\n"
        else:
            text += "* **Active Frontiers in Lane**: (none)\n"

        enabled_names, _ext_guide_text, _available_exts_text = _extensions_text(run_dir)
        if enabled_names:
            text += f"* **Enabled Extensions**: {', '.join(sorted(enabled_names))}\n"
    except Exception as exc:
        text += f"(context unavailable: {type(exc).__name__}: {exc})\n"
    return text


def build_extensions_guide(args) -> str:
    """Build the static-guide-only "## Managing Extensions" section.

    Includes the list of available-but-not-enabled extensions and the guide
    text contributed by enabled extensions. Not part of ``--context`` output —
    that mode only reports the enabled extension names (see
    :func:`build_current_context`).
    """
    from arctx_cli.context import resolve_run_id_from_args, resolve_store

    text = ""
    try:
        run_id = resolve_run_id_from_args(args)
        store = resolve_store(args.store_dir)
        run_dir = None
        if run_id:
            candidate = store.run_path(run_id)
            if candidate.exists():
                run_dir = str(candidate)

        ext_guide_text = ""
        available_exts_text = ""
        if run_dir:
            _enabled_names, ext_guide_text, available_exts_text = _extensions_text(run_dir)

        text += "\n## Managing Extensions\n"
        text += "Extensions add domain-specific workflows (e.g. `git`, `diagram`) to arctx.\n"
        text += "* List available extensions: `arctx ext list`\n"
        text += "* Enable an extension: `arctx ext enable <name>`\n"
        text += "* Disable an extension: `arctx ext disable <name>`\n"

        if available_exts_text:
            text += f"\n### Available Extensions (Not Enabled)\n{available_exts_text}"

        if ext_guide_text:
            text += f"\n## Enabled Extensions Commands\n{ext_guide_text}"
    except Exception:
        # The extensions section is purely informational; if it cannot be
        # built, the (mandatory) Current Context block below still reports
        # the failure visibly.
        pass
    return text


def cli_guide(args) -> int:
    if getattr(args, "context", False):
        print(build_current_context(args).strip("\n"))
        return 0

    guide_text = STATIC_GUIDE_TEXT
    guide_text += build_extensions_guide(args)
    guide_text += build_current_context(args)
    print(guide_text)
    return 0
