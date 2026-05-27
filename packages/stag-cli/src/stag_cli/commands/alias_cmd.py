"""stag alias subcommand — manage CLI aliases.

Subcommands
-----------
list     Show the current alias table with provenance (run > user > ext).
add      Add or update an alias in the user config.
remove   Remove an alias from the user config.
resolve  Show the expansion of a given alias token (debug helper).
"""

from __future__ import annotations

import argparse
import json
import sys


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``alias`` subcommand."""
    parser = subparsers.add_parser("alias", help="Manage CLI aliases")
    alias_sub = parser.add_subparsers(dest="alias_command", required=True)

    # alias list
    al_list = alias_sub.add_parser("list", help="Show all aliases with provenance")
    al_list.add_argument("--run", default=None, help="Run ID")
    al_list.add_argument("--store-dir", default=None, dest="store_dir")

    # alias add <name> <target>
    al_add = alias_sub.add_parser("add", help="Add or update a user alias")
    al_add.add_argument("name", help="Alias name (e.g. 'c')")
    al_add.add_argument("target", help="Alias target (e.g. 'git commit')")

    # alias remove <name>
    al_remove = alias_sub.add_parser("remove", help="Remove a user alias")
    al_remove.add_argument("name", help="Alias name to remove")

    # alias resolve <name>
    al_resolve = alias_sub.add_parser("resolve", help="Show how a token resolves")
    al_resolve.add_argument("name", help="Token to resolve")
    al_resolve.add_argument("--run", default=None, help="Run ID")
    al_resolve.add_argument("--store-dir", default=None, dest="store_dir")

    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_run_dir_from_args(args) -> str | None:
    """Best-effort: resolve run_dir from args."""
    from pathlib import Path

    store_dir = getattr(args, "store_dir", None)
    run_id_arg = getattr(args, "run", None)
    if run_id_arg is None:
        import os

        run_id_arg = os.environ.get("STAG_RUN_ID")
    if run_id_arg and store_dir:
        return str(Path(store_dir) / run_id_arg)
    if run_id_arg:
        from stag_cli.paths import resolve_store_dir

        return str(Path(resolve_store_dir()) / run_id_arg)
    return None


def _collect_ext_aliases(run_dir: str | None) -> tuple[list[dict[str, str]], list[str]]:
    """Load default_aliases from standard and enabled extensions."""
    from stag_api.ext import load_extension
    from stag_api.ext.enabled import load_enabled

    ext_aliases: list[dict[str, str]] = []
    ext_names: list[str] = []
    seen: set[str] = set()
    for ext_name in ["git"]:
        try:
            ext = load_extension(ext_name)
            ext_aliases.append(ext.default_aliases())
            ext_names.append(ext.name)
            seen.add(ext.name)
        except (KeyError, ImportError):
            continue

    if run_dir is None:
        return ext_aliases, ext_names

    for ee in load_enabled(run_dir):
        if ee.name in seen:
            continue
        try:
            ext = load_extension(ee.name)
            ext_aliases.append(ext.default_aliases())
            ext_names.append(ext.name)
            seen.add(ext.name)
        except (KeyError, ImportError):
            continue
    return ext_aliases, ext_names


# ---------------------------------------------------------------------------
# CLI dispatcher
# ---------------------------------------------------------------------------


def cli_alias(args) -> int:
    """Dispatch stag alias subcommands."""
    from stag_cli.alias import list_aliases, remove_user_alias, resolve_alias, save_user_alias

    cmd = args.alias_command

    if cmd == "list":
        run_dir = _resolve_run_dir_from_args(args)
        ext_aliases, ext_names = _collect_ext_aliases(run_dir)
        table = list_aliases(
            run_dir=run_dir,
            extensions_default_aliases=ext_aliases,
            extension_names=ext_names,
        )
        output = {
            name: {"target": target, "source": source}
            for name, (target, source) in table.items()
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    if cmd == "add":
        path = save_user_alias(args.name, args.target)
        print(f"alias {args.name!r} -> {args.target!r} saved to {path}", file=sys.stderr)
        return 0

    if cmd == "remove":
        try:
            path = remove_user_alias(args.name)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"alias {args.name!r} removed from {path}", file=sys.stderr)
        return 0

    if cmd == "resolve":
        run_dir = _resolve_run_dir_from_args(args)
        ext_aliases, _ = _collect_ext_aliases(run_dir)
        from stag_cli.alias import load_alias_table

        table = load_alias_table(run_dir=run_dir, extensions_default_aliases=ext_aliases)
        expanded = resolve_alias(table, [args.name])
        if expanded == [args.name]:
            result = {"input": args.name, "resolved": False, "tokens": expanded}
        else:
            source = "unknown"
            from stag_cli.alias import list_aliases as _la

            ext_aliases2, ext_names2 = _collect_ext_aliases(run_dir)
            provenance = _la(
                run_dir=run_dir,
                extensions_default_aliases=ext_aliases2,
                extension_names=ext_names2,
            )
            if args.name in provenance:
                source = provenance[args.name][1]
            result = {
                "input": args.name,
                "resolved": True,
                "tokens": expanded,
                "target": table[args.name],
                "source": source,
            }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    return 1
