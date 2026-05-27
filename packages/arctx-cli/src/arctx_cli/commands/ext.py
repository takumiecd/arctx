"""arctx ext subcommand — manage extensions for a run.

Subcommands
-----------
list    List all built-in extensions and whether each is enabled in the current run.
show    Show details (version, default_aliases) for a named extension as JSON.
enable  Enable an extension in an existing run (calls on_init, then records it).
disable Remove an extension from the enabled list (side effects are NOT reversed).
"""

from __future__ import annotations

import argparse
import json
import sys


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``ext`` subcommand."""
    parser = subparsers.add_parser("ext", help="Manage extensions")
    ext_sub = parser.add_subparsers(dest="ext_command", required=True)

    # ext list
    _list = ext_sub.add_parser("list", help="List available extensions")
    _list.add_argument("--run", default=None, help="Run ID")
    _list.add_argument("--store-dir", default=None, dest="store_dir")

    # ext show <name>
    show = ext_sub.add_parser("show", help="Show extension details")
    show.add_argument("name", help="Extension name")

    # ext enable <name>
    enable = ext_sub.add_parser("enable", help="Enable an extension in the current run")
    enable.add_argument("name", help="Extension name")
    enable.add_argument("--run", default=None, help="Run ID")
    enable.add_argument("--store-dir", default=None, dest="store_dir")

    # ext disable <name>
    disable = ext_sub.add_parser("disable", help="Disable an extension in the current run")
    disable.add_argument("name", help="Extension name")
    disable.add_argument("--run", default=None, help="Run ID")
    disable.add_argument("--store-dir", default=None, dest="store_dir")

    return parser


# ---------------------------------------------------------------------------
# Command runners
# ---------------------------------------------------------------------------


def run_ext_list_command(
    *,
    run_dir: str | None = None,
) -> dict:
    """Return info about all built-in extensions.

    Parameters
    ----------
    run_dir:
        When provided, each extension's enabled status is checked against
        the run's ``extensions.json``.
    """
    from arctx.ext import list_available
    from arctx.ext.enabled import load_enabled

    available = list_available()
    enabled_names: set[str] = set()
    if run_dir is not None:
        enabled_names = {ee.name for ee in load_enabled(run_dir)}

    items = []
    for name in available:
        items.append({"name": name, "enabled": name in enabled_names})
    return {"extensions": items}


def run_ext_show_command(name: str) -> dict:
    """Return details for a named extension.

    Raises
    ------
    KeyError
        If *name* is not registered.
    """
    from arctx.ext import load_extension

    ext = load_extension(name)
    return {
        "name": ext.name,
        "version": ext.version,
        "default_aliases": ext.default_aliases(),
    }


def run_ext_enable_command(
    *,
    name: str,
    run_dir: str,
) -> dict:
    """Enable extension *name* in *run_dir*.

    Calls ``on_init`` with an empty options dict (no parser options available
    after init), then records the extension as enabled.

    Raises
    ------
    KeyError
        If *name* is not in the registry.
    """
    from arctx.ext import load_extension
    from arctx.ext.base import InitContext
    from arctx.ext.enabled import EnabledExtension, add_enabled, load_enabled
    from arctx.storage.jsonl import JsonlRunStore

    # Resolve run_id from the run dir (read run.json)
    import json as _json
    from pathlib import Path as _Path

    run_json = _Path(run_dir) / "run.json"
    run_id = _json.loads(run_json.read_text(encoding="utf-8"))["run_id"]

    ext = load_extension(name)

    # Check if already enabled
    current = load_enabled(run_dir)
    if any(e.name == name for e in current):
        return {"status": "already_enabled", "name": name}

    ctx = InitContext(run_id=run_id, run_dir=run_dir, options={})
    ext.on_init(ctx)

    add_enabled(run_dir, EnabledExtension(name=ext.name, version=ext.version, config={}))
    return {"status": "enabled", "name": name}


def run_ext_disable_command(
    *,
    name: str,
    run_dir: str,
) -> dict:
    """Remove extension *name* from the enabled list.

    Does NOT reverse any side effects (files written, hooks installed, etc.).
    Callers should warn the user about this.

    Raises
    ------
    KeyError
        If *name* is not currently enabled.
    """
    from arctx.ext.enabled import load_enabled, save_enabled

    current = load_enabled(run_dir)
    remaining = [e for e in current if e.name != name]
    if len(remaining) == len(current):
        raise KeyError(f"extension {name!r} is not enabled in this run")
    save_enabled(run_dir, remaining)
    return {"status": "disabled", "name": name}


# ---------------------------------------------------------------------------
# CLI dispatcher
# ---------------------------------------------------------------------------


def _resolve_run_dir(args) -> str | None:
    """Best-effort: resolve run_dir from args."""
    from pathlib import Path

    store_dir = getattr(args, "store_dir", None)
    run_id_arg = getattr(args, "run", None)
    if run_id_arg is None:
        import os

        run_id_arg = os.environ.get("ARCTX_RUN_ID")
    if run_id_arg and store_dir:
        return str(Path(store_dir) / run_id_arg)
    if run_id_arg:
        from arctx_cli.paths import resolve_store_dir

        return str(Path(resolve_store_dir()) / run_id_arg)
    return None


def cli_ext(args) -> int:
    """Dispatch arctx ext subcommands."""
    cmd = args.ext_command

    if cmd == "list":
        run_dir = _resolve_run_dir(args)
        result = run_ext_list_command(run_dir=run_dir)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if cmd == "show":
        try:
            result = run_ext_show_command(args.name)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if cmd == "enable":
        run_dir = _resolve_run_dir(args)
        if run_dir is None:
            print("error: cannot resolve run directory. Pass --run and --store-dir.", file=sys.stderr)
            return 1
        try:
            result = run_ext_enable_command(name=args.name, run_dir=run_dir)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        status = result["status"]
        if status == "already_enabled":
            print(f"warning: {args.name!r} is already enabled", file=sys.stderr)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if cmd == "disable":
        run_dir = _resolve_run_dir(args)
        if run_dir is None:
            print("error: cannot resolve run directory. Pass --run and --store-dir.", file=sys.stderr)
            return 1
        try:
            result = run_ext_disable_command(name=args.name, run_dir=run_dir)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"warning: side effects of {args.name!r} are NOT reversed (files remain)", file=sys.stderr)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    return 1
