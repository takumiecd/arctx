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
produced it, `Payload` = the data attached to either. Nodes are never created
standalone — a node is born only as a step's output.

**One grammar, three bundles.** Everything that groups records is a flat name:
a **lane** bundles work, a **table** bundles measured numbers (trials), a
**topic** bundles meaning. Writing a new name creates the bundle, every view is
derived at read time, the latest summary / best row is the current state, and
`cut` is the append-only eraser. Learn the grammar once and all three behave
the same.

## Writing

1. **Open a lane and walk.** `arctx lane create NAME --purpose "why"` then
   `arctx lane switch NAME`. Each record of progress is one step:
   `arctx add --type <TYPE> --title "..." --field key=value` (omit `--from` to
   continue from the lane's single frontier; repeat `--from` to join). When the
   step is a *scored attempt*, record it as a trial instead so the numbers are
   comparable: `arctx trial add --table NAME --col k=v --metric k=v`
   (optimize extension; tables are born on first use, columns grow, only a
   column's value kind is fixed by its first row). A sweep is one step, not
   one per attempt: add `--to <STEP_ID>` to hang another row on the step you
   already made, or `--rows FILE.jsonl` to write the whole batch at once.
2. **Keep summaries current.** `arctx lane summarize NAME --summary "..."` is
   the lane's position; `arctx topic summarize NAME --summary "..."` is what
   the run currently believes about a subject (latest wins, history stays).
   Closing a lane requires its conclusion: `arctx lane close NAME --summary`.
3. **Tag meaning as you notice it.** `arctx topic tag NAME <ID> [<ID> ...]`
   marks any nodes/steps as belonging to a subject — connectivity is *not*
   required. When a topic's records sit in several unjoined regions, the topic
   view shows them as islands: a candidate, not an error, with four ways out —
   `topic join NAME --summary` (both right, verdict on the new node),
   `topic split NAME --island N --into NEW` (two subjects all along),
   `cut <ID>` (that one was a dead end), `topic untag NAME <ID>` (wrong tag).
   **Which lineage is right is a judgement, not something the data settles:
   ask before you pick.** Writing a statement from one island while the
   current one speaks for another is refused, because "latest wins" would
   drop a live conclusion.

Corrections are append-only: `arctx cut <ID>` retires a record (`uncut`
reverses), `arctx reparent <NODE>` swaps a node's producer. Nothing is deleted.

## Reading

* **"Where am I, what is known?"** → `arctx guide --context`: run, current
  lane + summary, active frontiers, current topic statements. Cheap enough to
  call at the start of every turn.
* **"What has been tried about X?"** → `arctx explore --query "TERMS"` — the
  primary retrieval path; position-independent AND search over lanes and every
  payload (tags and summaries included). Hits print snippets and jumpable ids.
* **"Which attempt was best?"** → `arctx trials [TABLE] [--sort COL |
  --best min:COL]`; **"what do we believe about X?"** → `arctx topics` /
  `arctx topic NAME`.
* **"What happened here?"** → `arctx dump --format outline`, `arctx log`,
  `arctx show <ID>`.

## Other commands worth knowing

* `arctx attach <ID> --type <TYPE> --field key=value` : attach a generic
  payload to a node or step.
* `arctx asset attach <ID> <PATH> [--commit REF]` : reference a committed file
  or directory — `(commit, path)`, never a copy; commit the file first.
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

        # Current knowledge: latest statement per topic, so an agent starts
        # with the run's established findings instead of re-deriving them.
        from arctx.core.topics import list_topics

        all_views = list_topics(handle.run_graph)
        views = [view for view in all_views if view.summary]
        if views:
            text += "* **Topics (current statements)**:\n"
            for view in views[:5]:
                text += f"  - `{view.name}`: {collapse_summary(view.summary.text)}\n"
            if len(views) > 5:
                text += f"  - … {len(views) - 5} more — `arctx topics`\n"

        # A split subject is standing debt like an open lane: name it every
        # time, so reconciling is a visible chore rather than a surprise.
        split = [view for view in all_views if len(view.islands) > 1]
        if split:
            text += "* **Topics split across unjoined islands**:\n"
            for view in split[:5]:
                text += (
                    f"  - `{view.name}`: {len(view.islands)} islands — "
                    f"`arctx topic {view.name}` shows what each one concluded\n"
                )
            text += (
                "  - which lineage is right is a question for the user, not a "
                "guess — ask, then `topic join` / `split` / `cut` / `untag`\n"
            )
            if len(split) > 5:
                text += f"  - … {len(split) - 5} more — `arctx topics`\n"

        # Lane hygiene: finished work deserves a written conclusion. Surface
        # open lanes nobody has written to in a while, so closing them is a
        # visible chore instead of silent debt.
        from arctx.core.lanes import stale_open_lanes

        stale = stale_open_lanes(handle.run_graph)
        if stale:
            names = ", ".join(
                f"`{lane.name or lane.lane_id}` ({idle}d)" for lane, _, idle in stale[:5]
            )
            more = f" +{len(stale) - 5} more" if len(stale) > 5 else ""
            text += (
                f"* **Stale open lanes (close them!)**: {names}{more} — "
                'conclude with `arctx lane close NAME --summary "..."`\n'
            )

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
