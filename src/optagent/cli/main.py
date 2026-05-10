"""optagent CLI entry point."""

from __future__ import annotations

import argparse
import sys

from optagent.cli.commands.current import add_parser as add_current_parser, cli_current
from optagent.cli.commands.dump import add_parser as add_dump_parser, cli_dump
from optagent.cli.commands.guide import add_parser as add_guide_parser, cli_guide
from optagent.cli.commands.init import add_parser as add_init_parser, cli_init
from optagent.cli.commands.list import add_parser as add_list_parser, cli_list
from optagent.cli.commands.note import add_parser as add_note_parser, cli_note
from optagent.cli.commands.observe import add_parser as add_observe_parser, cli_observe
from optagent.cli.commands.outcomes import add_parser as add_outcomes_parser, cli_outcomes
from optagent.cli.commands.plan import add_parser as add_plan_parser, cli_plan
from optagent.cli.commands.predict import add_parser as add_predict_parser, cli_predict
from optagent.cli.commands.reachable import add_parser as add_reachable_parser, cli_reachable
from optagent.cli.commands.rewind import add_parser as add_rewind_parser, cli_rewind
from optagent.cli.commands.show import add_parser as add_show_parser, cli_show
from optagent.cli.commands.trace import add_parser as add_trace_parser, cli_trace
from optagent.cli.commands.use import add_parser as add_use_parser, cli_use
from optagent.cli.commands.view import add_parser as add_view_parser, cli_view


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optagent",
        description="Record optimization and problem-solving processes",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_current_parser(subparsers)
    add_dump_parser(subparsers)
    add_guide_parser(subparsers)
    add_init_parser(subparsers)
    add_list_parser(subparsers)
    add_note_parser(subparsers)
    add_observe_parser(subparsers)
    add_outcomes_parser(subparsers)
    add_plan_parser(subparsers)
    add_predict_parser(subparsers)
    add_reachable_parser(subparsers)
    add_rewind_parser(subparsers)
    add_show_parser(subparsers)
    add_trace_parser(subparsers)
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

    if args.command == "current":
        return cli_current(args)
    if args.command == "dump":
        return cli_dump(args)
    if args.command == "guide":
        return cli_guide(args)
    if args.command == "init":
        return cli_init(args)
    if args.command == "list":
        return cli_list(args)
    if args.command == "note":
        return cli_note(args)
    if args.command == "observe":
        return cli_observe(args)
    if args.command == "outcomes":
        return cli_outcomes(args)
    if args.command == "plan":
        return cli_plan(args)
    if args.command == "predict":
        return cli_predict(args)
    if args.command == "reachable":
        return cli_reachable(args)
    if args.command == "rewind":
        return cli_rewind(args)
    if args.command == "show":
        return cli_show(args)
    if args.command == "trace":
        return cli_trace(args)
    if args.command == "use":
        return cli_use(args)
    if args.command == "view":
        return cli_view(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
