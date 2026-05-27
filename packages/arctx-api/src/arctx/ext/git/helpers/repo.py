"""Thin subprocess wrapper for Git operations.

All functions accept an explicit ``repo_root`` path and run git commands
inside it. They raise ``subprocess.CalledProcessError`` on non-zero exit
unless the docstring says otherwise.

The only public side effect is reading from the repository; nothing here
writes git state.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ARCTX_GIT_WORKTREE_ENV = "ARCTX_GIT_WORKTREE"


def resolve_worktree_path(explicit: str | Path | None = None) -> Path:
    """Return the git working tree that arctx git operations should target.

    Resolution order:
    1. *explicit* argument when provided.
    2. ``ARCTX_GIT_WORKTREE`` environment variable.
    3. The current working directory.

    The path is not validated here; callers that need ``git`` to succeed
    will surface ``subprocess.CalledProcessError`` if the location is
    not a real worktree.
    """
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get(ARCTX_GIT_WORKTREE_ENV)
    if env:
        return Path(env)
    return Path.cwd()


def common_dir(cwd: str | Path | None = None) -> Path:
    """Return the shared ``.git`` directory for the repository.

    Inside a worktree, ``git rev-parse --git-common-dir`` resolves to the
    primary checkout's ``.git`` rather than the per-worktree pointer file,
    so two worktrees of the same repo report the same path.
    """
    raw = _git(["rev-parse", "--git-common-dir"], cwd or ".")
    path = Path(raw)
    if not path.is_absolute():
        path = (Path(cwd or ".") / path).resolve()
    return path


def primary_worktree_root(cwd: str | Path | None = None) -> Path:
    """Return the path of the repository's primary (non-linked) worktree."""
    raw = _git(["worktree", "list", "--porcelain"], cwd or ".")
    first_path: str | None = None
    for line in raw.splitlines():
        if line.startswith("worktree "):
            first_path = line[len("worktree "):]
            break
    if not first_path:
        return find_repo_root(cwd)
    return Path(first_path).resolve()


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


def resolve_commit(repo_root: str | Path, commit: str) -> str:
    """Return the full SHA for *commit* if it resolves to a commit object."""
    return _git(["rev-parse", "--verify", f"{commit}^{{commit}}"], repo_root)


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
    Uses a record-separator approach: each commit is rendered as 4 lines
    (sha / subject / author / date) separated by ``\x1e`` (ASCII RS char),
    and commits are separated by ``\x1f`` (ASCII US char).
    """
    # Use ASCII record-separator and unit-separator which git supports as
    # literals in --format strings.
    rs = "\x1e"   # record separator between fields within a commit
    us = "\x1f"   # unit separator between commits
    fmt = f"%H{rs}%s{rs}%aN{rs}%aI{us}"
    try:
        raw = _git(
            ["log", f"{base_commit}..HEAD", f"--format={fmt}"],
            repo_root,
        )
    except subprocess.CalledProcessError:
        # base_commit may not be an ancestor in a fresh repo; treat as empty
        return []

    if not raw:
        return []

    entries = []
    for block in raw.split(us):
        block = block.strip()
        if not block:
            continue
        parts = block.split(rs, 3)
        if len(parts) < 4:
            continue
        sha, subject, author, date = parts[0], parts[1], parts[2], parts[3]
        entries.append({
            "sha": sha.strip(),
            "subject": subject.strip(),
            "author": author.strip(),
            "date": date.strip(),
        })
    return entries


def commit_log_for_commits(repo_root: str | Path, commits: list[str] | tuple[str, ...]) -> list[dict[str, str]]:
    """Return commit metadata for explicit commit SHAs in the given order."""
    if not commits:
        return []
    rs = "\x1e"
    entries = []
    for commit in commits:
        fmt = f"%H{rs}%s{rs}%aN{rs}%aI"
        raw = _git(["show", "--no-patch", f"--format={fmt}", commit], repo_root)
        parts = raw.split(rs, 3)
        if len(parts) < 4:
            continue
        sha, subject, author, date = parts[0], parts[1], parts[2], parts[3]
        entries.append({
            "sha": sha.strip(),
            "subject": subject.strip(),
            "author": author.strip(),
            "date": date.strip(),
        })
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


def diff_shortstat_for_commits(repo_root: str | Path, commits: list[str] | tuple[str, ...]) -> dict[str, int]:
    """Return aggregate shortstat for explicit commits."""
    result = {"files_changed": 0, "insertions": 0, "deletions": 0}
    for commit in commits:
        raw = _git(["show", "--shortstat", "--format=", commit], repo_root)
        m = re.search(r"(\d+) files? changed", raw)
        if m:
            result["files_changed"] += int(m.group(1))
        m = re.search(r"(\d+) insertion", raw)
        if m:
            result["insertions"] += int(m.group(1))
        m = re.search(r"(\d+) deletion", raw)
        if m:
            result["deletions"] += int(m.group(1))
    return result


def diff_name_only(repo_root: str | Path, base_commit: str) -> list[str]:
    """Return list of changed file paths from ``git diff --name-only base..HEAD``."""
    try:
        raw = _git(["diff", "--name-only", f"{base_commit}..HEAD"], repo_root)
    except subprocess.CalledProcessError:
        return []
    return [line for line in raw.splitlines() if line]


def diff_name_only_for_commits(repo_root: str | Path, commits: list[str] | tuple[str, ...]) -> list[str]:
    """Return sorted unique file paths changed by explicit commits."""
    files: set[str] = set()
    for commit in commits:
        raw = _git(["show", "--format=", "--name-only", commit], repo_root)
        files.update(line for line in raw.splitlines() if line)
    return sorted(files)


def diff_patch(repo_root: str | Path, base_commit: str) -> str:
    """Return unified diff text from ``git diff base_commit..HEAD``.

    Returns empty string when there is no diff.
    """
    try:
        raw = _git(["diff", f"{base_commit}..HEAD"], repo_root)
    except subprocess.CalledProcessError:
        return ""
    return raw


def diff_patch_for_commits(repo_root: str | Path, commits: list[str] | tuple[str, ...]) -> str:
    """Return concatenated patch text for explicit commits."""
    if not commits:
        return ""
    return _git(["show", "--format=medium", "--patch", *commits], repo_root)
