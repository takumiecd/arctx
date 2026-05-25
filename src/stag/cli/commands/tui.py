"""stag CLI tui command."""

from __future__ import annotations

import argparse
import importlib.util
import sys

from stag.cli.context import resolve_store


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("tui", help="Launch the Textual UI")
    parser.add_argument("--store-dir", default=".stag/runs")
    return parser


def cli_tui(args) -> int:
    if importlib.util.find_spec("textual") is None:
        print("Error: 'textual' required. pip install textual", file=sys.stderr)
        return 1
    from stag.tui.app import StagApp

    store = resolve_store(args.store_dir)
    StagApp(store=store).run()
    return 0
