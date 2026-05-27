"""stag CLI entry point."""

from __future__ import annotations

import argparse
import sys

from stag.cli.commands.alias_cmd import add_parser as add_alias_parser
from stag.cli.commands.alias_cmd import cli_alias
from stag.cli.commands.anchor import add_parser as add_anchor_parser
from stag.cli.commands.anchor import cli_anchor
from stag.cli.commands.current import add_parser as add_current_parser
from stag.cli.commands.current import cli_current
from stag.cli.commands.cut import add_parser as add_cut_parser
from stag.cli.commands.cut import cli_cut
from stag.cli.commands.dump import add_parser as add_dump_parser
from stag.cli.commands.dump import cli_dump
from stag.cli.commands.ext import add_parser as add_ext_parser
from stag.cli.commands.ext import cli_ext
from stag.cli.commands.graph import add_parser as add_graph_parser
from stag.cli.commands.graph import cli_graph
from stag.cli.commands.guide import add_parser as add_guide_parser
from stag.cli.commands.guide import cli_guide
from stag.cli.commands.init import add_parser as add_init_parser
from stag.cli.commands.init import cli_init
from stag.cli.commands.list import add_parser as add_list_parser
from stag.cli.commands.list import cli_list
from stag.cli.commands.migrate import add_parser as add_migrate_parser
from stag.cli.commands.migrate import cli_migrate
from stag.cli.commands.node import add_parser as add_node_parser
from stag.cli.commands.node import cli_node
from stag.cli.commands.outcomes import add_parser as add_outcomes_parser
from stag.cli.commands.outcomes import cli_outcomes
from stag.cli.commands.payload import add_parser as add_payload_parser
from stag.cli.commands.payload import cli_payload
from stag.cli.commands.reachable import add_parser as add_reachable_parser
from stag.cli.commands.reachable import cli_reachable
from stag.cli.commands.show import add_parser as add_show_parser
from stag.cli.commands.show import cli_show
from stag.cli.commands.sync import add_parser as add_sync_parser
from stag.cli.commands.sync import cli_sync
from stag.cli.commands.trace import add_parser as add_trace_parser
from stag.cli.commands.trace import cli_trace
from stag.cli.commands.transition import add_parser as add_transition_parser
from stag.cli.commands.transition import cli_transition
from stag.cli.commands.tui import add_parser as add_tui_parser
from stag.cli.commands.tui import cli_tui
from stag.cli.commands.use import add_parser as add_use_parser
from stag.cli.commands.use import cli_use
from stag.cli.commands.view import add_parser as add_view_parser
from stag.cli.commands.view import cli_view
from stag.cli.commands.work_session import (
    add_parser as add_work_session_parser,
)
from stag.cli.commands.work_session import (
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
    add_current_parser(subparsers)
    add_ext_parser(subparsers)
    add_dump_parser(subparsers)
    add_graph_parser(subparsers)
    add_guide_parser(subparsers)
    add_init_parser(subparsers)
    add_list_parser(subparsers)
    add_migrate_parser(subparsers)
    add_node_parser(subparsers)
    add_outcomes_parser(subparsers)
    add_payload_parser(subparsers)
    add_reachable_parser(subparsers)
    add_cut_parser(subparsers)
    add_show_parser(subparsers)
    add_sync_parser(subparsers)
    add_tui_parser(subparsers)
    add_trace_parser(subparsers)
    add_transition_parser(subparsers)
    add_use_parser(subparsers)
    add_view_parser(subparsers)
    add_work_session_parser(subparsers)

    from stag.ext import register_standard_cli  # noqa: PLC0415

    register_standard_cli(subparsers)

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
    """Load default_aliases from standard and enabled extensions."""
    from stag.ext import load_extension  # noqa: PLC0415
    from stag.ext.enabled import load_enabled  # noqa: PLC0415

    ext_aliases: list[dict[str, str]] = []
    seen: set[str] = set()
    for ext_name in ["git"]:
        try:
            ext = load_extension(ext_name)
            ext_aliases.append(ext.default_aliases())
            seen.add(ext.name)
        except (KeyError, ImportError):
            continue

    if run_dir is None:
        return ext_aliases

    for ee in load_enabled(run_dir):
        if ee.name in seen:
            continue
        try:
            ext = load_extension(ee.name)
            ext_aliases.append(ext.default_aliases())
            seen.add(ext.name)
        except (KeyError, ImportError):
            continue
    return ext_aliases


def parse_args(argv: list[str] | None = None):
    """Parse CLI arguments."""
    parser = _build_parser()
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI entry point."""
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
    handler = getattr(args, "_stag_handler", None)
    if handler is not None:
        return handler(args)

    if args.command == "alias":
        return cli_alias(args)
    if args.command == "anchor":
        return cli_anchor(args)
    if args.command == "current":
        return cli_current(args)
    if args.command == "dump":
        return cli_dump(args)
    if args.command == "ext":
        return cli_ext(args)
    if args.command == "graph":
        return cli_graph(args)
    if args.command == "guide":
        return cli_guide(args)
    if args.command == "init":
        return cli_init(args)
    if args.command == "list":
        return cli_list(args)
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
    if args.command == "view":
        return cli_view(args)
    if args.command == "work-session":
        return cli_work_session(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
