"""STAG path resolution for the git-native storage layout.

Run data lives outside the repo under STAG_HOME:
  ${STAG_HOME}/runs/<uuid>/

The "active run" pointer is a single file inside the git directory
(``<gitdir>/stag-id``, one UUID line). It lives under ``.git/`` so git
itself never tracks it: there is no risk of accidental commits and no
``.gitignore`` plumbing is required. For ``git worktree`` checkouts the
pointer naturally ends up in the per-worktree gitdir, so each worktree
keeps its own active run.

Resolution priority for STAG_HOME:
  1. STAG_HOME env var
  2. $XDG_DATA_HOME/stag
  3. ~/.local/share/stag
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_stag_home() -> Path:
    """Resolve STAG_HOME.

    Priority:
    1. ``STAG_HOME`` env var
    2. ``$XDG_DATA_HOME/stag``
    3. ``~/.local/share/stag``
    """
    env_home = os.environ.get("STAG_HOME")
    if env_home:
        return Path(env_home)
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "stag"
    return Path.home() / ".local" / "share" / "stag"


def runs_dir() -> Path:
    """Return ``<stag_home>/runs``."""
    return resolve_stag_home() / "runs"


def resolve_git_dir(repo_root: Path) -> Path:
    """Return the real gitdir for *repo_root*.

    For a normal clone this is ``<repo_root>/.git``. For a linked
    worktree, ``<repo_root>/.git`` is a file containing
    ``gitdir: <path>`` and we follow it.
    """
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        text = dot_git.read_text(encoding="utf-8").strip()
        for line in text.splitlines():
            if line.startswith("gitdir:"):
                target = Path(line.split(":", 1)[1].strip())
                if not target.is_absolute():
                    target = (repo_root / target).resolve()
                return target
    # Fallback: behave as if it were a directory (callers will error on
    # write if it truly does not exist).
    return dot_git


def stag_id_path(repo_root: Path) -> Path:
    """Return the path to the active-run pointer for *repo_root*.

    The pointer lives at ``<gitdir>/stag-id`` so git itself never tracks
    it.
    """
    return resolve_git_dir(repo_root) / "stag-id"


def read_stag_id(repo_root: Path) -> str | None:
    """Read the run id from the active-run pointer if present, else None.

    For one release we also fall back to the legacy ``<repo_root>/.stag-id``
    location and silently migrate it into the gitdir on read, so existing
    checkouts keep working.
    """
    path = stag_id_path(repo_root)
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        return text if text else None

    legacy = repo_root / ".stag-id"
    if legacy.exists():
        text = legacy.read_text(encoding="utf-8").strip()
        if not text:
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
            legacy.unlink()
        except OSError:
            pass
        return text
    return None


def write_stag_id(repo_root: Path, run_id: str) -> None:
    """Write *run_id* to the active-run pointer for *repo_root*."""
    path = stag_id_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run_id + "\n", encoding="utf-8")
    # Clean up any stale legacy file if present.
    legacy = repo_root / ".stag-id"
    if legacy.exists():
        try:
            legacy.unlink()
        except OSError:
            pass


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: cwd) to find a ``.git`` entry.

    Accepts both a ``.git`` directory (normal clone) and a ``.git`` file
    (linked worktree).

    Raises
    ------
    RuntimeError
        If no ``.git`` entry is found before reaching the filesystem root.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            raise RuntimeError(
                "not inside a git repository (no .git directory found). "
                "Run 'git init' first, or provide --run / STAG_RUN_ID."
            )
        current = parent


def resolve_store_dir() -> str:
    """Return the string path of ``<stag_home>/runs``.

    This is the new default store_dir replacing the old ``.stag/runs``.
    """
    return str(runs_dir())
