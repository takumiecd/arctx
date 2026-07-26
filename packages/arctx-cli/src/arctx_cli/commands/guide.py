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

`arctx` records the *process* of optimization and problem-solving as a DAG that
lives in this repository. `Node` = a state reached, `Step` = a transition that
produced it, `Payload` = the data attached to either. A `Lane` is a flat unit of
work, like a git branch — lanes have no parents and no children.

## Writing: three verbs

1. **Open a lane.** `arctx lane create NAME --purpose "why"`, then
   `arctx lane switch NAME`. One lane per line of attack; fan independent
   approaches out from the same baseline Node instead of serializing them.
2. **`arctx add`.** Every record of progress is one Step plus its output Node:
   `arctx add --from <NODE> --type <TYPE> --field key=value`. Repeat `--from`
   for a multi-input join. Omit `--from` to use the current lane's single active
   frontier (on a fresh run it falls back to the untouched run root, so the very
   first `add` needs no `--from`); zero or several frontiers is an error that
   tells you what to pass. Nodes are never created standalone.
3. **Close with a summary.** `arctx lane close NAME --summary "<synthesis>"`.
   The summary is required and *is* the conclusion — do not write a separate
   synthesis step and then close on top of it. One leaf → it stamps that leaf;
   several leaves → it merges them into one node. A closed lane refuses writes
   until `arctx lane open NAME`. Mid-work, refresh the lane's current summary
   with `arctx lane summarize NAME --summary "..."` (stays open).

Corrections are append-only: `arctx cut <ID>` retires a Node or Step (`uncut`
reverses it), and `arctx reparent <NODE> --from <NEW_INPUT>...` reconnects a
node to new inputs by adding a new producing Step and cutting the old one —
descendants are preserved. Nothing is ever deleted.

## Reading: three questions

* **"What is happening now?"** → `arctx guide --context`. Run, current lane,
  its purpose and current summary, active frontiers, enabled extensions. Cheap
  enough to call at the start of every turn.
* **"What has been tried about X?"** → `arctx explore --query "TERMS"`. This is
  the primary retrieval path: case-insensitive AND search over lane names and
  every payload a lane owns. Position-independent — no current lane needed, no
  hierarchy to walk. Each hit prints a snippet and the ids to jump to.
  `arctx explore` alone lists lanes one line each (closed ones folded; `--all`
  to include them); `arctx explore LANE` shows one lane in full.
* **"What happened here?"** → `arctx dump --format outline` for the graph
  (`--lane` to narrow), `arctx log` for a chronological read, and
  `arctx show <ID>` for one Node / Step / Payload.

## Other commands worth knowing

* `arctx attach <NODE_OR_STEP> --type <TYPE> --field key=value` : attach a
  generic payload (`--payload-type summary` for a typed summary).
* `arctx asset attach <NODE_OR_STEP> <PATH> [--commit REF]` : reference a
  committed file or directory (default commit: HEAD). Assets are `(commit,
  path)` references, never copies — commit the file first. `arctx asset show
  <PAYLOAD>` reports whether the reference still resolves in this clone.
* `arctx export --format json|md` : the shareable document / GUI data contract.
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
    """Build the "## Current Context" block — the answer to "what is happening
    now": Run ID, run purpose, the current lane (name / status / purpose /
    current summary), its active frontiers, and enabled extension names.

    Lanes are flat, so there is no ancestor chain to print: everything an agent
    needs to resume is either on this lane or one ``arctx explore --query``
    away. This is the single source of dynamic context, shared by the full
    guide (``arctx guide``) and the dynamic-only mode (``arctx guide
    --context``) so the two never drift. Never raises: any failure to resolve
    context is folded into a visible ``(context unavailable: ...)`` note
    instead of being silently swallowed, so an agent can tell when context is
    missing.
    """
    from arctx.core.lanes import collapse_summary, lane_current_summary, lane_purpose

    from arctx_cli.commands._lane_context import find_lane
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
        run_purpose = handle.run_graph.metadata.get("purpose")
        if run_purpose:
            text += f"* **Run Purpose**: {run_purpose}\n"

        lane_id = resolve_lane_id_from_args(args)
        context = resolve_lane_frontiers(handle, lane_id)
        lane_label = context.lane_name or context.lane_id
        lane = find_lane(handle, lane_id)
        # The implicit "default" lane has no Lane record, so there is no status
        # to report for it — printing `[unknown]` would be noise, not context.
        status = f" [{lane.status}]" if lane is not None else ""
        text += f"* **Current Lane**: `{lane_label}`{status}\n"
        if lane is not None:
            purpose = lane_purpose(lane)
            if purpose:
                text += f"  - purpose: {purpose}\n"
            summary = lane_current_summary(
                handle.run_graph, lane.lane_id, root_node_id=handle.root_node_id
            )
            if summary is not None:
                text += f"  - current summary: {collapse_summary(summary.text)}\n"

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
