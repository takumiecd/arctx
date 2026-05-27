"""CLI-side extension registration.

Keeps the stag_api layer free of CLI dependencies.  ``stag_cli.main``
calls :func:`register_enabled_cli` to attach argparse subparsers for each
extension that is enabled in the current run directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def register_extension_cli(subparsers, names: Iterable[str]) -> None:
    """Register CLI namespaces provided by the named extensions."""
    from stag_api.ext import load_extension
    from stag_cli.commands import register_cli_commands

    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        ext = load_extension(name)
        register_cli_commands(subparsers, ext.cli_commands())
        seen.add(ext.name)


def register_enabled_cli(subparsers, run_dir: str | Path | None) -> None:
    """Register CLI namespaces for extensions enabled in a run directory."""
    if run_dir is None:
        return
    from stag_api.ext.enabled import load_enabled

    register_extension_cli(subparsers, (item.name for item in load_enabled(run_dir)))
