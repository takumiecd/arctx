"""stag CLI entry point."""

from __future__ import annotations

import argparse
import sys

from stag.cli.commands.anchor import add_parser as add_anchor_parser, cli_anchor
from stag.cli.commands.current import add_parser as add_current_parser, cli_current
from stag.cli.commands.dump import add_parser as add_dump_parser, cli_dump
from stag.cli.commands.git import add_parser as add_git_parser, cli_git
from stag.cli.commands.guide import add_parser as add_guide_parser, cli_guide
from stag.cli.commands.init import add_parser as add_init_parser, cli_init
from stag.cli.commands.list import add_parser as add_list_parser, cli_list
from stag.cli.commands.outcomes import add_parser as add_outcomes_parser, cli_outcomes
from stag.cli.commands.reachable import add_parser as add_reachable_parser, cli_reachable
from stag.cli.commands.cut import add_parser as add_cut_parser, cli_cut
from stag.cli.commands.show import add_parser as add_show_parser, cli_show
from stag.cli.commands.sync import add_parser as add_sync_parser, cli_sync
from stag.cli.commands.trace import add_parser as add_trace_parser, cli_trace
from stag.cli.commands.migrate import add_parser as add_migrate_parser, cli_migrate
from stag.cli.commands.transition import add_parser as add_transition_parser, cli_transition
from stag.cli.commands.use import add_parser as add_use_parser, cli_use
from stag.cli.commands.tui import add_parser as add_tui_parser, cli_tui
from stag.cli.commands.view import add_parser as add_view_parser, cli_view


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stag",
        description="Record optimization and problem-solving processes",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_anchor_parser(subparsers)
    add_current_parser(subparsers)
    add_dump_parser(subparsers)
    add_git_parser(subparsers)
    add_guide_parser(subparsers)
    add_init_parser(subparsers)
    add_list_parser(subparsers)
    add_migrate_parser(subparsers)
    add_outcomes_parser(subparsers)
    add_reachable_parser(subparsers)
    add_cut_parser(subparsers)
    add_show_parser(subparsers)
    add_sync_parser(subparsers)
    add_tui_parser(subparsers)
    add_trace_parser(subparsers)
    add_transition_parser(subparsers)
    add_use_parser(subparsers)
    add_view_parser(subparsers)

    return parser


def parse_args(argv: list[str] | None = None):
    """Parse CLI arguments."""
    parser = _build_parser()
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    args = parse_args(argv)

    if args.command == "anchor":
        return cli_anchor(args)
    if args.command == "current":
        return cli_current(args)
    if args.command == "dump":
        return cli_dump(args)
    if args.command == "git":
        return cli_git(args)
    if args.command == "guide":
        return cli_guide(args)
    if args.command == "init":
        return cli_init(args)
    if args.command == "list":
        return cli_list(args)
    if args.command == "migrate":
        return cli_migrate(args)
    if args.command == "outcomes":
        return cli_outcomes(args)
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

    return 1


if __name__ == "__main__":
    sys.exit(main())
