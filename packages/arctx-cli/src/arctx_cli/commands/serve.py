"""arctx CLI serve command: a local read/write HTTP API for one run.

This is the live-mode backend for GUI surfaces. ``GET /run`` returns the same
JSON document as ``arctx export --format json``; the ``POST`` routes write
through the same verbs as ``arctx add`` / ``arctx cut``. See
:mod:`arctx_cli.serve` for the route table.
"""

from __future__ import annotations

import argparse

from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)
from arctx_cli.serve import serve


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "serve",
        help="Serve one run over a local read/write HTTP API (for GUIs)",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8787,
                        help="Bind port (default: 8787)")
    parser.add_argument("--cors-origin", default="*",
                        help="Access-Control-Allow-Origin value (default: *)")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--work-session", default=None)
    return parser


def cli_serve(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    serve(
        store,
        run_id,
        host=args.host,
        port=args.port,
        user_id=resolve_user_id_from_args(args),
        work_session_id=resolve_work_session_id_from_args(args),
        cors_origin=args.cors_origin,
    )
    return 0
