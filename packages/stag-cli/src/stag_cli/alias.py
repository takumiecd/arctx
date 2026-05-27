"""Alias resolution for stag CLI.

Resolution priority (later wins for the same key when merging):
1. Extension default_aliases (load order; first ext wins among ext-default conflicts)
2. User config (~/.config/stag/aliases.toml)
3. Run-local config (<run_dir>/aliases.toml)

Alias expansion is one-level only — alias-to-alias chains are prohibited to
prevent infinite loops.

Format of aliases.toml::

    [aliases]
    commit = "git commit"
    c = "git commit"
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    import tomllib  # py311+ stdlib
except ModuleNotFoundError:  # py310 fallback
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError as exc:
        raise ImportError(
            "Python 3.10 requires the 'tomli' package for TOML parsing. "
            "Install it with: pip install tomli"
        ) from exc


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _user_alias_path() -> Path:
    """Return ``~/.config/stag/aliases.toml``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "stag" / "aliases.toml"
    return Path.home() / ".config" / "stag" / "aliases.toml"


def _run_alias_path(run_dir: Path | str) -> Path:
    """Return ``<run_dir>/aliases.toml``."""
    return Path(run_dir) / "aliases.toml"


# ---------------------------------------------------------------------------
# TOML writer (minimal — stdlib has no tomllib writer)
# ---------------------------------------------------------------------------


def _write_toml_aliases(path: Path, aliases: dict[str, str]) -> None:
    """Write *aliases* to *path* as a ``[aliases]`` TOML section.

    Entries are sorted for stable output.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[aliases]\n"]
    for key in sorted(aliases.keys()):
        value = aliases[key].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key} = "{value}"\n')
    path.write_text("".join(lines), encoding="utf-8")


def _read_toml_aliases(path: Path) -> dict[str, str]:
    """Read the ``[aliases]`` table from *path*.  Returns {} if missing."""
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    raw = data.get("aliases", {})
    return {str(k): str(v) for k, v in raw.items()}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_alias_table(
    *,
    run_dir: str | Path | None = None,
    extensions_default_aliases: Optional[list[dict[str, str]]] = None,
) -> dict[str, str]:
    """Build the merged alias table.

    Priority (later entries win for the same key):
    - Extension defaults (in load order; first ext wins for ext-level conflicts)
    - User config (~/.config/stag/aliases.toml)
    - Run-local config (<run_dir>/aliases.toml)

    Parameters
    ----------
    run_dir:
        Directory of the active run.  When provided, ``<run_dir>/aliases.toml``
        is loaded and takes highest priority.
    extensions_default_aliases:
        List of ``default_aliases()`` dicts from enabled extensions, in load
        order.  First ext wins for duplicate alias names at this tier.
    """
    merged: dict[str, str] = {}

    # 1. Extension defaults (first ext wins → iterate in order, skip if already set)
    if extensions_default_aliases:
        for ext_aliases in extensions_default_aliases:
            for name, target in ext_aliases.items():
                if name not in merged:
                    merged[name] = target

    # 2. User config (overrides ext defaults)
    user_aliases = _read_toml_aliases(_user_alias_path())
    merged.update(user_aliases)

    # 3. Run-local config (highest priority)
    if run_dir is not None:
        run_aliases = _read_toml_aliases(_run_alias_path(run_dir))
        merged.update(run_aliases)

    return merged


def resolve_alias(alias_table: dict[str, str], tokens: list[str]) -> list[str]:
    """Expand *tokens[0]* if it appears in *alias_table*; else return *tokens*.

    Expansion is one-level only.  The alias value is split on whitespace (no
    shell quoting support needed for now) and prepended to the remaining tokens.

    Examples
    --------
    >>> resolve_alias({"commit": "git commit"}, ["commit", "-m", "x"])
    ["git", "commit", "-m", "x"]
    >>> resolve_alias({}, ["init", "req"])
    ["init", "req"]
    """
    if not tokens:
        return tokens
    first = tokens[0]
    if first not in alias_table:
        return tokens
    expansion = alias_table[first].split()
    return expansion + tokens[1:]


def save_user_alias(name: str, target: str) -> Path:
    """Add or update *name → target* in the user aliases.toml.

    Returns the path of the written file.
    """
    path = _user_alias_path()
    existing = _read_toml_aliases(path)
    existing[name] = target
    _write_toml_aliases(path, existing)
    return path


def remove_user_alias(name: str) -> Path:
    """Remove *name* from the user aliases.toml.

    Returns the path of the written file.

    Raises
    ------
    KeyError
        If *name* is not present.
    """
    path = _user_alias_path()
    existing = _read_toml_aliases(path)
    if name not in existing:
        raise KeyError(f"alias not found: {name!r}")
    del existing[name]
    _write_toml_aliases(path, existing)
    return path


def list_aliases(
    *,
    run_dir: str | Path | None = None,
    extensions_default_aliases: Optional[list[dict[str, str]]] = None,
    extension_names: Optional[list[str]] = None,
) -> dict[str, tuple[str, str]]:
    """Return ``{alias_name: (target, source)}`` with provenance.

    *source* is one of:

    - ``"run"`` — from ``<run_dir>/aliases.toml``
    - ``"user"`` — from ``~/.config/stag/aliases.toml``
    - ``"ext:<name>"`` — from an extension's ``default_aliases()``

    The same merge priority applies; this function exposes the winning source
    for each alias name.

    Parameters
    ----------
    extension_names:
        Parallel list to *extensions_default_aliases* giving the extension name
        for each entry.  If None, sources are labelled ``"ext:0"``, ``"ext:1"``
        etc.
    """
    result: dict[str, tuple[str, str]] = {}

    ext_aliases_list = extensions_default_aliases or []
    ext_names_list = extension_names or []

    # 1. Extension defaults (first ext wins)
    for idx, ext_aliases in enumerate(ext_aliases_list):
        ext_label = f"ext:{ext_names_list[idx]}" if idx < len(ext_names_list) else f"ext:{idx}"
        for name, target in ext_aliases.items():
            if name not in result:
                result[name] = (target, ext_label)

    # 2. User config
    user_aliases = _read_toml_aliases(_user_alias_path())
    for name, target in user_aliases.items():
        result[name] = (target, "user")

    # 3. Run-local (highest priority)
    if run_dir is not None:
        run_aliases = _read_toml_aliases(_run_alias_path(run_dir))
        for name, target in run_aliases.items():
            result[name] = (target, "run")

    return result


__all__ = [
    "load_alias_table",
    "resolve_alias",
    "save_user_alias",
    "remove_user_alias",
    "list_aliases",
]
