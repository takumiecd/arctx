"""arctx-tui command entry point."""

from __future__ import annotations

import argparse

from arctx.session import resolve_store
from arctx_tui.app import ArctxApp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arctx-tui", description="Launch the ARCTX TUI")
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
    args = parser.parse_args(argv)
    store = resolve_store(args.store_dir)
    watch_interval = None if args.no_watch else args.watch_interval
    ArctxApp(store=store, watch_interval=watch_interval).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
