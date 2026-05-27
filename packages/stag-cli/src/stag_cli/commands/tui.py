"""stag CLI tui command."""

from __future__ import annotations

import argparse
import importlib.util
import sys

from stag_cli.context import resolve_store


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("tui", help="Launch the Textual UI")
    parser.add_argument("--store-dir", default=None)
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=2.0,
        help="Seconds between automatic run refresh checks",
    )
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="Disable automatic refresh checks",
    )
    return parser


def cli_tui(args) -> int:
    if importlib.util.find_spec("textual") is None:
        print("Error: 'textual' required. pip install textual", file=sys.stderr)
        return 1
    from stag_cli.tui.app import StagApp

    store = resolve_store(args.store_dir)
    watch_interval = None if args.no_watch else args.watch_interval
    StagApp(store=store, watch_interval=watch_interval).run()
    return 0
