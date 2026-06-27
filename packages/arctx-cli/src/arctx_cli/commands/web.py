"""Serve the bundled ARCTX web GUI for one run."""

from __future__ import annotations

import argparse
import sys
import webbrowser

from arctx.web.assets import find_static_dir
from arctx.web.extensions import load_enabled_routes, load_enabled_scripts
from arctx.web.server import serve_gui

from arctx_cli.context import (
    require_existing_run_from_args,
    resolve_lane_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("web", help="Serve the bundled web GUI for one run")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8788, help="Bind port (default: 8788)")
    parser.add_argument("--cors-origin", default="*", help="Access-Control-Allow-Origin value (default: *)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--lane", default=None)
    return parser


def cli_web(args) -> int:
    static_dir = find_static_dir()
    if static_dir is None:
        print(
            "arctx web: no built frontend found.\n"
            "  Build it first:  npm --prefix web install && npm --prefix web run build\n"
            "  or point at one: ARCTX_WEB_STATIC=/path/to/dist arctx web",
            file=sys.stderr,
        )
        return 1

    store = resolve_store(args.store_dir)
    run_id = require_existing_run_from_args(args, store)

    extension_scripts = load_enabled_scripts(store.run_path(run_id))
    extension_routes = load_enabled_routes(store.run_path(run_id))

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
        lane_id=resolve_lane_id_from_args(args),
        extension_scripts=extension_scripts,
        extension_routes=extension_routes,
        cors_origin=args.cors_origin,
        on_ready=_open,
    )
    return 0
