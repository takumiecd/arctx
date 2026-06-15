"""``arctx-gui`` entry point.

Resolves a run (reusing arctx-cli's run/user resolution), locates the built
frontend, serves both over HTTP, and opens a browser.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser

from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)

from arctx_gui.assets import find_static_dir
from arctx_gui.server import serve_gui


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arctx-gui",
        description="Serve the arctx web GUI for one run (read/write).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8788, help="Bind port (default: 8788)")
    parser.add_argument("--cors-origin", default="*",
                        help="Access-Control-Allow-Origin value (default: *)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open a browser automatically")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--work-session", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    static_dir = find_static_dir()
    if static_dir is None:
        print(
            "arctx-gui: no built frontend found.\n"
            "  Build it first:  npm --prefix gui install && npm --prefix gui run build\n"
            "  or bundle it:    python -m arctx_gui.bundle\n"
            "  or point at one: ARCTX_GUI_STATIC=/path/to/dist arctx-gui",
            file=sys.stderr,
        )
        return 1

    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    if not store.run_path(run_id).exists():
        print(f"arctx-gui: unknown run_id: {run_id}", file=sys.stderr)
        return 1

    def _open(url: str) -> None:
        if not args.no_browser:
            webbrowser.open(url)

    serve_gui(
        store,
        run_id,
        static_dir=static_dir,
        host=args.host,
        port=args.port,
        user_id=resolve_user_id_from_args(args),
        work_session_id=resolve_work_session_id_from_args(args),
        cors_origin=args.cors_origin,
        on_ready=_open,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
