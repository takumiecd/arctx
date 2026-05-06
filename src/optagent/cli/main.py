"""optagent CLI entry point."""

from __future__ import annotations

import argparse
import sys

from optagent.cli.commands.init import add_parser as add_init_parser, cli_init
from optagent.cli.commands.list import add_parser as add_list_parser, cli_list
from optagent.cli.commands.observe import add_parser as add_observe_parser, cli_observe
from optagent.cli.commands.plan import add_parser as add_plan_parser, cli_plan
from optagent.cli.commands.predict import add_parser as add_predict_parser, cli_predict
from optagent.cli.commands.promote import add_parser as add_promote_parser, cli_promote
from optagent.cli.commands.derive import add_parser as add_derive_parser, cli_derive
from optagent.cli.commands.refresh import add_parser as add_refresh_parser, cli_refresh
from optagent.cli.commands.state import add_parser as add_state_parser, cli_state
from optagent.cli.commands.show import add_parser as add_show_parser, cli_show
from optagent.cli.commands.trace import add_parser as add_trace_parser, cli_trace


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optagent",
        description="State-transition optimization agent framework",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_init_parser(subparsers)
    add_list_parser(subparsers)
    add_observe_parser(subparsers)
    add_plan_parser(subparsers)
    add_predict_parser(subparsers)
    add_promote_parser(subparsers)
    add_derive_parser(subparsers)
    add_refresh_parser(subparsers)
    add_show_parser(subparsers)
    add_state_parser(subparsers)
    add_trace_parser(subparsers)

    return parser


def parse_args(argv: list[str] | None = None):
    """Parse CLI arguments."""
    parser = _build_parser()
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    args = parse_args(argv)

    if args.command == "init":
        return cli_init(args)
    if args.command == "list":
        return cli_list(args)
    if args.command == "observe":
        return cli_observe(args)
    if args.command == "plan":
        return cli_plan(args)
    if args.command == "predict":
        return cli_predict(args)
    if args.command == "promote":
        return cli_promote(args)
    if args.command == "derive":
        return cli_derive(args)
    if args.command == "refresh":
        return cli_refresh(args)
    if args.command == "show":
        return cli_show(args)
    if args.command == "state":
        return cli_state(args)
    if args.command == "trace":
        return cli_trace(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
