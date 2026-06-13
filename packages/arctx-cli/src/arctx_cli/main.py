"""arctx CLI entry point."""

from __future__ import annotations

import argparse
import sys

from arctx_cli.commands import core_cli_commands, register_cli_commands


def _build_parser(*, run_dir: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arctx",
        description="Record optimization and problem-solving processes",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_cli_commands(subparsers, core_cli_commands())

    from arctx_cli.ext_registry import (  # noqa: PLC0415
        ALWAYS_ON_EXTENSIONS,
        register_enabled_cli,
        register_extension_cli,
    )

    register_extension_cli(subparsers, ALWAYS_ON_EXTENSIONS)
    register_enabled_cli(subparsers, run_dir)

    return parser


def _resolve_run_dir_for_alias(tokens: list[str]) -> str | None:
    """Best-effort resolution of run_dir for alias loading.

    Reads ``--run`` / ``ARCTX_RUN_ID`` / ``<gitdir>/arctx-id``. Returns None if no
    run can be resolved without side-effects.
    """
    import os
    from pathlib import Path

    # Look for --run <id> in tokens
    run_id: str | None = None
    store_dir: str | None = None
    for i, tok in enumerate(tokens):
        if tok == "--run" and i + 1 < len(tokens):
            run_id = tokens[i + 1]
        if tok == "--store-dir" and i + 1 < len(tokens):
            store_dir = tokens[i + 1]
        if tok.startswith("--run="):
            run_id = tok[6:]
        if tok.startswith("--store-dir="):
            store_dir = tok[12:]

    if run_id is None:
        run_id = os.environ.get("ARCTX_RUN_ID")

    if run_id is None:
        # Try <gitdir>/arctx-id
        try:
            from arctx_cli.paths import find_repo_root, read_arctx_id  # noqa: PLC0415

            repo_root = find_repo_root()
            run_id = read_arctx_id(repo_root)
        except Exception:  # noqa: BLE001
            pass

    if run_id is None:
        return None

    if store_dir is None:
        try:
            from arctx_cli.paths import resolve_store_dir  # noqa: PLC0415

            store_dir = resolve_store_dir()
        except Exception:  # noqa: BLE001
            return None

    candidate = Path(store_dir) / run_id
    return str(candidate) if candidate.is_dir() else None


def _collect_ext_default_aliases(run_dir: str | None) -> list[dict[str, str]]:
    """Load default_aliases from extensions enabled in the current run."""
    from arctx.ext import load_extension  # noqa: PLC0415
    from arctx.ext.enabled import load_enabled  # noqa: PLC0415

    ext_aliases: list[dict[str, str]] = []
    seen: set[str] = set()
    if run_dir is None:
        return ext_aliases

    for ee in load_enabled(run_dir):
        if ee.name in seen:
            continue
        try:
            ext = load_extension(ee.name)
            ext_aliases.append(ext.default_aliases())
            seen.add(ext.name)
        except (KeyError, ImportError):
            continue
    return ext_aliases


def parse_args(argv: list[str] | None = None):
    """Parse CLI arguments."""
    tokens: list[str] | None = None if argv is None else list(argv)
    run_dir = _resolve_run_dir_for_alias(tokens or sys.argv[1:])
    parser = _build_parser(run_dir=run_dir)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI entry point."""
    tokens: list[str] = list(argv if argv is not None else sys.argv[1:])

    # --- Alias resolution (one level only) ---
    run_dir = _resolve_run_dir_for_alias(tokens)
    ext_aliases = _collect_ext_default_aliases(run_dir)
    from arctx_cli.alias import load_alias_table, resolve_alias  # noqa: PLC0415

    alias_table = load_alias_table(
        run_dir=run_dir,
        extensions_default_aliases=ext_aliases,
    )
    tokens = resolve_alias(alias_table, tokens)
    # ---

    parser = _build_parser(run_dir=run_dir)
    args = parser.parse_args(tokens)
    handler = getattr(args, "_arctx_handler", None)
    if handler is not None:
        return handler(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
