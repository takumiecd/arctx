"""stag CLI entry point."""

from __future__ import annotations

import argparse
import sys

from stag.cli.commands.alias_cmd import add_parser as add_alias_parser, cli_alias
from stag.cli.commands.anchor import add_parser as add_anchor_parser, cli_anchor
from stag.cli.commands.branch import add_parser as add_branch_parser, cli_branch
from stag.cli.commands.cherry_pick import add_parser as add_cherry_pick_parser, cli_cherry_pick
from stag.cli.commands.commit import add_parser as add_commit_parser, cli_commit
from stag.cli.commands.hook import add_parser as add_hook_parser, cli_hook
from stag.cli.commands.current import add_parser as add_current_parser, cli_current
from stag.cli.commands.dump import add_parser as add_dump_parser, cli_dump
from stag.cli.commands.ext import add_parser as add_ext_parser, cli_ext
from stag.cli.commands.git import add_parser as add_git_parser, cli_git
from stag.cli.commands.graph import add_parser as add_graph_parser, cli_graph
from stag.cli.commands.guide import add_parser as add_guide_parser, cli_guide
from stag.cli.commands.init import add_parser as add_init_parser, cli_init
from stag.cli.commands.list import add_parser as add_list_parser, cli_list
from stag.cli.commands.node import add_parser as add_node_parser, cli_node
from stag.cli.commands.outcomes import add_parser as add_outcomes_parser, cli_outcomes
from stag.cli.commands.payload import add_parser as add_payload_parser, cli_payload
from stag.cli.commands.reachable import add_parser as add_reachable_parser, cli_reachable
from stag.cli.commands.reset import add_parser as add_reset_parser, cli_reset
from stag.cli.commands.revert import add_parser as add_revert_parser, cli_revert
from stag.cli.commands.cut import add_parser as add_cut_parser, cli_cut
from stag.cli.commands.show import add_parser as add_show_parser, cli_show
from stag.cli.commands.sync import add_parser as add_sync_parser, cli_sync
from stag.cli.commands.trace import add_parser as add_trace_parser, cli_trace
from stag.cli.commands.merge import add_parser as add_merge_parser, cli_merge
from stag.cli.commands.migrate import add_parser as add_migrate_parser, cli_migrate
from stag.cli.commands.transition import add_parser as add_transition_parser, cli_transition
from stag.cli.commands.use import add_parser as add_use_parser, cli_use
from stag.cli.commands.tui import add_parser as add_tui_parser, cli_tui
from stag.cli.commands.verify import add_parser as add_verify_parser, cli_verify
from stag.cli.commands.view import add_parser as add_view_parser, cli_view
from stag.cli.commands.work_session import (
    add_parser as add_work_session_parser,
    cli_work_session,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stag",
        description="Record optimization and problem-solving processes",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_alias_parser(subparsers)
    add_anchor_parser(subparsers)
    add_branch_parser(subparsers)
    add_cherry_pick_parser(subparsers)
    add_commit_parser(subparsers)
    add_current_parser(subparsers)
    add_ext_parser(subparsers)
    add_hook_parser(subparsers)
    add_dump_parser(subparsers)
    add_git_parser(subparsers)
    add_graph_parser(subparsers)
    add_guide_parser(subparsers)
    add_init_parser(subparsers)
    add_list_parser(subparsers)
    add_merge_parser(subparsers)
    add_migrate_parser(subparsers)
    add_node_parser(subparsers)
    add_outcomes_parser(subparsers)
    add_payload_parser(subparsers)
    add_reachable_parser(subparsers)
    add_reset_parser(subparsers)
    add_revert_parser(subparsers)
    add_cut_parser(subparsers)
    add_show_parser(subparsers)
    add_sync_parser(subparsers)
    add_tui_parser(subparsers)
    add_trace_parser(subparsers)
    add_verify_parser(subparsers)
    add_transition_parser(subparsers)
    add_use_parser(subparsers)
    add_view_parser(subparsers)
    add_work_session_parser(subparsers)

    return parser


def _resolve_run_dir_for_alias(tokens: list[str]) -> str | None:
    """Best-effort resolution of run_dir for alias loading.

    Reads ``--run`` / ``STAG_RUN_ID`` / ``.stag-id``.  Returns None if no
    run can be resolved without side-effects.
    """
    import os
    from pathlib import Path

    # Look for --run <id> in tokens
    run_id: str | None = None
    store_dir: str | None = None
    for i, tok in enumerate(tokens):
        if tok == "--run" and i + 1 < len(tokens):
            run_id = tokens[i + 1]
        if tok == "--store-dir" and i + 1 < len(tokens):
            store_dir = tokens[i + 1]
        if tok.startswith("--run="):
            run_id = tok[6:]
        if tok.startswith("--store-dir="):
            store_dir = tok[12:]

    if run_id is None:
        run_id = os.environ.get("STAG_RUN_ID")

    if run_id is None:
        # Try .stag-id
        try:
            from stag.cli.paths import find_repo_root, read_stag_id  # noqa: PLC0415

            repo_root = find_repo_root()
            run_id = read_stag_id(repo_root)
        except Exception:  # noqa: BLE001
            pass

    if run_id is None:
        return None

    if store_dir is None:
        try:
            from stag.cli.paths import resolve_store_dir  # noqa: PLC0415

            store_dir = resolve_store_dir()
        except Exception:  # noqa: BLE001
            return None

    candidate = Path(store_dir) / run_id
    return str(candidate) if candidate.is_dir() else None


def _collect_ext_default_aliases(run_dir: str | None) -> list[dict[str, str]]:
    """Load default_aliases from enabled extensions; ignore failures."""
    if run_dir is None:
        return []

    from stag.ext import load_extension  # noqa: PLC0415
    from stag.ext.enabled import load_enabled  # noqa: PLC0415

    ext_aliases: list[dict[str, str]] = []
    for ee in load_enabled(run_dir):
        try:
            ext = load_extension(ee.name)
            ext_aliases.append(ext.default_aliases())
        except (KeyError, ImportError):
            continue
    return ext_aliases


def parse_args(argv: list[str] | None = None):
    """Parse CLI arguments."""
    parser = _build_parser()
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    tokens: list[str] = list(argv if argv is not None else sys.argv[1:])

    # --- Alias resolution (one level only) ---
    run_dir = _resolve_run_dir_for_alias(tokens)
    ext_aliases = _collect_ext_default_aliases(run_dir)
    from stag.cli.alias import load_alias_table, resolve_alias  # noqa: PLC0415

    alias_table = load_alias_table(
        run_dir=run_dir,
        extensions_default_aliases=ext_aliases,
    )
    tokens = resolve_alias(alias_table, tokens)
    # ---

    args = parse_args(tokens)

    if args.command == "alias":
        return cli_alias(args)
    if args.command == "anchor":
        return cli_anchor(args)
    if args.command == "branch":
        return cli_branch(args)
    if args.command == "cherry-pick":
        return cli_cherry_pick(args)
    if args.command == "commit":
        return cli_commit(args)
    if args.command == "current":
        return cli_current(args)
    if args.command == "dump":
        return cli_dump(args)
    if args.command == "ext":
        return cli_ext(args)
    if args.command == "git":
        return cli_git(args)
    if args.command == "graph":
        return cli_graph(args)
    if args.command == "hook":
        return cli_hook(args)
    if args.command == "guide":
        return cli_guide(args)
    if args.command == "init":
        return cli_init(args)
    if args.command == "list":
        return cli_list(args)
    if args.command == "merge":
        return cli_merge(args)
    if args.command == "migrate":
        return cli_migrate(args)
    if args.command == "node":
        return cli_node(args)
    if args.command == "outcomes":
        return cli_outcomes(args)
    if args.command == "payload":
        return cli_payload(args)
    if args.command == "reachable":
        return cli_reachable(args)
    if args.command == "reset":
        return cli_reset(args)
    if args.command == "revert":
        return cli_revert(args)
    if args.command == "cut":
        return cli_cut(args)
    if args.command == "show":
        return cli_show(args)
    if args.command == "sync":
        return cli_sync(args)
    if args.command == "tui":
        return cli_tui(args)
    if args.command == "trace":
        return cli_trace(args)
    if args.command == "transition":
        return cli_transition(args)
    if args.command == "use":
        return cli_use(args)
    if args.command == "verify":
        return cli_verify(args)
    if args.command == "view":
        return cli_view(args)
    if args.command == "work-session":
        return cli_work_session(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
