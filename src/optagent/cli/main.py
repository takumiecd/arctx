"""optagent CLI entry point."""

from __future__ import annotations

import argparse
import sys

from optagent.cli.commands.init import add_parser as add_init_parser, cli_init
from optagent.cli.commands.plan import add_parser as add_plan_parser, cli_plan


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optagent",
        description="State-transition optimization agent framework",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_init_parser(subparsers)
    add_plan_parser(subparsers)

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
    if args.command == "plan":
        return cli_plan(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
