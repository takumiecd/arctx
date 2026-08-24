"""Alias resolution for arctx CLI.

Resolution priority (later wins for the same key when merging):
1. Extension default_aliases (load order; first ext wins among ext-default conflicts)
2. User config (~/.config/arctx/aliases.toml)

An alias only ever comes from code the user installed or a file in the user's
own home. There is deliberately no run-local tier: a run lives in a repository
and travels with it, so `<run_dir>/aliases.toml` was attacker-controlled data
read at the highest priority. An alias like `show = "cut node"` turned a read
command into an append-only write on a received run, overriding even the
victim's own aliases, and the file was not in `.arctx/.gitignore`. Nothing in
the product ever wrote one.

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
    except ModuleNotFoundError:
        # Do not take the whole CLI down for a feature this invocation may not
        # use. `main()` imports this module before argparse runs, so raising
        # here killed even `arctx --help`. Alias files are simply unreadable
        # without a parser; every other command works.
        tomllib = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _user_alias_path() -> Path:
    """Return ``~/.config/arctx/aliases.toml``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "arctx" / "aliases.toml"
    return Path.home() / ".config" / "arctx" / "aliases.toml"


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
    if tomllib is None:
        import sys

        print(
            f"notice: ignoring {path} — no TOML parser on this interpreter "
            "(pip install tomli)",
            file=sys.stderr,
        )
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
    - User config (~/.config/arctx/aliases.toml)

    Parameters
    ----------
    run_dir:
        Directory of the active run.  Kept because extension defaults are
        resolved per run; no alias file is read from it.
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

    - ``"user"`` — from ``~/.config/arctx/aliases.toml``
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

    return result



def resolve_run_dir_for_alias(tokens: list[str]) -> str | None:
    """Best-effort resolution of run_dir for alias loading.

    Reads ``--run`` / ``ARCTX_RUN_ID`` / ``<gitdir>/arctx-id`` — the documented
    order — and returns None if no run resolves without side-effects.

    This is the one resolver. `arctx alias list` / `alias resolve` used to have
    their own, which stopped at ``ARCTX_RUN_ID`` and never consulted
    ``<gitdir>/arctx-id``. Inside a repo with a run pointer and no env var the
    two disagreed, so the alias-introspection commands reported a different
    resolution than the CLI actually dispatched.
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

__all__ = [
    "load_alias_table",
    "resolve_run_dir_for_alias",
    "resolve_alias",
    "save_user_alias",
    "remove_user_alias",
    "list_aliases",
]
