"""optagent CLI entry point."""

from __future__ import annotations

import argparse
import sys

from optagent.cli.commands.init import cli_init
from optagent.cli.commands.plan import cli_plan


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optagent",
        description="State-transition optimization agent framework",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init subcommand
    init_parser = subparsers.add_parser("init", help="Initialize a new run")
    init_parser.add_argument("requirement_id", help="Requirement identifier")
    init_parser.add_argument(
        "--target-type",
        default="code",
        help="Target category (default: code)",
    )
    init_parser.add_argument(
        "--target-id",
        default=None,
        help="Specific target identifier (default: requirement_id)",
    )
    init_parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit run id (default: auto-generated)",
    )
    init_parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory to save runs (default: .optagent/runs)",
    )

    # plan subcommand
    plan_parser = subparsers.add_parser("plan", help="Create plans from current state")
    plan_parser.add_argument("run_id", help="Run identifier")
    plan_parser.add_argument(
        "--planner",
        default="default",
        help="Planner name (default: default)",
    )
    plan_parser.add_argument(
        "--max-plans",
        type=int,
        default=1,
        help="Maximum number of plans to create (default: 1)",
    )
    plan_parser.add_argument(
        "--action-type",
        default="analysis",
        help="Action category for the plan (default: analysis)",
    )
    plan_parser.add_argument(
        "--intent",
        default=None,
        help="Description of what the plan does",
    )
    plan_parser.add_argument(
        "--input",
        action="append",
        help="Plan input as key=value (can be given multiple times)",
    )
    plan_parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )

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
