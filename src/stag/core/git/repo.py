"""Thin subprocess wrapper for Git operations.

All functions accept an explicit ``repo_root`` path and run git commands
inside it. They raise ``subprocess.CalledProcessError`` on non-zero exit
unless the docstring says otherwise.

The only public side effect is reading from the repository; nothing here
writes git state.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _git(args: list[str], cwd: str | Path) -> str:
    """Run ``git *args`` in *cwd* and return stdout as a stripped string."""
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            ["git"] + args,
            result.stdout,
            result.stderr,
        )
    return result.stdout.strip()


def find_repo_root(cwd: str | Path | None = None) -> Path:
    """Return the absolute path to the git repository root.

    Uses ``git rev-parse --show-toplevel``.

    Raises
    ------
    subprocess.CalledProcessError
        If the current directory is not inside a git repository.
    """
    raw = _git(["rev-parse", "--show-toplevel"], cwd or ".")
    return Path(raw).resolve()


def current_commit(repo_root: str | Path) -> str:
    """Return the full SHA of HEAD."""
    return _git(["rev-parse", "HEAD"], repo_root)


def current_branch(repo_root: str | Path) -> str | None:
    """Return the current branch name, or None if HEAD is detached.

    Uses ``git symbolic-ref --short HEAD``; a non-zero exit indicates
    detached HEAD.
    """
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def is_detached_head(repo_root: str | Path) -> bool:
    """Return True if HEAD is in detached state."""
    return current_branch(repo_root) is None


def status_lines(repo_root: str | Path) -> list[str]:
    """Return output lines of ``git status --porcelain``."""
    raw = _git(["status", "--porcelain"], repo_root)
    return [line for line in raw.splitlines() if line]


def is_dirty(repo_root: str | Path) -> bool:
    """Return True if tracked files have modifications, staged, or deletions.

    Untracked files (lines starting with ``??``) are excluded per spec.
    """
    for line in status_lines(repo_root):
        xy = line[:2]
        if xy != "??" and xy.strip():
            return True
    return False


def untracked_count(repo_root: str | Path) -> int:
    """Return the number of untracked files."""
    return sum(1 for line in status_lines(repo_root) if line.startswith("??"))


def commit_log(repo_root: str | Path, base_commit: str) -> list[dict[str, str]]:
    """Return commits in ``base_commit..HEAD`` as a list of dicts.

    Each dict has keys: sha, subject, author, date (ISO 8601 with timezone).
    Uses ``--format=%H%x00%s%x00%aN%x00%aI`` (NUL-separated fields, one
    commit per line using a non-ambiguous separator).
    """
    sep = "\x00"
    fmt = f"%H{sep}%s{sep}%aN{sep}%aI"
    try:
        raw = _git(
            ["log", f"{base_commit}..HEAD", f"--format={fmt}", "--no-walk=unsorted"],
            repo_root,
        )
    except subprocess.CalledProcessError:
        # base_commit may not be an ancestor in a fresh repo; treat as empty
        return []

    if not raw:
        return []

    entries = []
    for line in raw.splitlines():
        parts = line.split(sep, 3)
        if len(parts) < 4:
            continue
        sha, subject, author, date = parts
        entries.append({"sha": sha, "subject": subject, "author": author, "date": date})
    return entries


def diff_shortstat(repo_root: str | Path, base_commit: str) -> dict[str, int]:
    """Return ``git diff --shortstat base_commit..HEAD`` as a dict.

    Keys: ``files_changed``, ``insertions``, ``deletions``.
    Returns all zeros when there is no diff.
    """
    try:
        raw = _git(["diff", "--shortstat", f"{base_commit}..HEAD"], repo_root)
    except subprocess.CalledProcessError:
        return {"files_changed": 0, "insertions": 0, "deletions": 0}

    if not raw:
        return {"files_changed": 0, "insertions": 0, "deletions": 0}

    result = {"files_changed": 0, "insertions": 0, "deletions": 0}

    m = re.search(r"(\d+) files? changed", raw)
    if m:
        result["files_changed"] = int(m.group(1))
    m = re.search(r"(\d+) insertion", raw)
    if m:
        result["insertions"] = int(m.group(1))
    m = re.search(r"(\d+) deletion", raw)
    if m:
        result["deletions"] = int(m.group(1))
    return result


def diff_name_only(repo_root: str | Path, base_commit: str) -> list[str]:
    """Return list of changed file paths from ``git diff --name-only base..HEAD``."""
    try:
        raw = _git(["diff", "--name-only", f"{base_commit}..HEAD"], repo_root)
    except subprocess.CalledProcessError:
        return []
    return [line for line in raw.splitlines() if line]


def diff_patch(repo_root: str | Path, base_commit: str) -> str:
    """Return unified diff text from ``git diff base_commit..HEAD``.

    Returns empty string when there is no diff.
    """
    try:
        raw = _git(["diff", f"{base_commit}..HEAD"], repo_root)
    except subprocess.CalledProcessError:
        return ""
    return raw
