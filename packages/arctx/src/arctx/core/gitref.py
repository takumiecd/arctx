"""Git object plumbing for ``(commit, path)`` asset references.

ARCTX is git-native: run data lives inside the repository and an *asset* is
nothing but a reference to a git object — ``(commit, path)`` where ``path`` is
repo-root-relative and may name a blob **or** a tree. Nothing is copied; the
bytes are resolved from git at read time.

This module is deliberately stdlib-only (``subprocess`` + ``mimetypes``) and
core-level, mirroring :mod:`arctx.paths` which already resolves the enclosing
repository. It is not part of the optional ``git`` *extension*: the extension
records commits as history, whereas this module is the read path that core
payloads (``AssetPayload``) and the serve layer depend on.

Per the git-native "absent = self" convention there is no repo field on an
asset: the repository is always the one enclosing the run data.
"""

from __future__ import annotations

import mimetypes
import subprocess
from dataclasses import dataclass
from pathlib import Path

from arctx.paths import find_repo_root

__all__ = [
    "GitRefError",
    "MissingCommit",
    "MissingPath",
    "TreeEntry",
    "guess_content_type",
    "normalize_repo_path",
    "object_kind",
    "read_blob",
    "list_tree",
    "resolve_commit",
    "repo_root_for",
    "head_commit",
    "unpushed_warning",
]


class GitRefError(Exception):
    """Base error for git object resolution failures."""


class MissingCommit(GitRefError):  # noqa: N818 - reads as a status, not an error type
    """The referenced commit does not exist in this clone."""


class MissingPath(GitRefError):  # noqa: N818 - reads as a status, not an error type
    """The referenced path does not exist at the referenced commit."""


@dataclass(frozen=True)
class TreeEntry:
    """One entry of a git tree listing."""

    name: str
    path: str
    kind: str  # "blob" | "tree" | "commit" (submodule)
    mode: str
    oid: str
    size: int | None = None

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "mode": self.mode,
            "oid": self.oid,
            "size": self.size,
        }


# ---------------------------------------------------------------------------
# subprocess helpers
# ---------------------------------------------------------------------------


def _git_text(args: list[str], repo_root: str | Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise GitRefError(message or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _git_bytes(args: list[str], repo_root: str | Path) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
    )
    if result.returncode != 0:
        message = (result.stderr or b"").decode("utf-8", "replace").strip()
        raise GitRefError(message or f"git {' '.join(args)} failed")
    return result.stdout


def _git_ok(args: list[str], repo_root: str | Path) -> bool:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# repo / path resolution
# ---------------------------------------------------------------------------


def repo_root_for(start: str | Path | None = None) -> Path:
    """Return the repository root enclosing *start* (default: cwd).

    Raises
    ------
    GitRefError
        When *start* is not inside a git repository.

    """
    probe = Path(start) if start is not None else None
    if probe is not None and not probe.is_dir():
        probe = probe.parent
    try:
        return find_repo_root(probe)
    except RuntimeError as exc:
        raise GitRefError(
            "not inside a git repository: assets are references to git objects, "
            "so the run must live in a repo"
        ) from exc


def normalize_repo_path(path: str | Path, *, repo_root: str | Path | None = None) -> str:
    """Return *path* as a clean repo-root-relative POSIX path.

    Accepts a path relative to the repo root, an absolute path inside the
    repo, or (when *repo_root* is given) a path relative to the current
    working directory. ``""``/``"."`` mean the repository root tree.
    """
    raw = Path(path)
    if repo_root is not None:
        root = Path(repo_root).resolve()
        candidate = raw if raw.is_absolute() else (Path.cwd() / raw)
        try:
            resolved = candidate.resolve()
        except OSError:  # pragma: no cover - defensive
            resolved = candidate
        if resolved == root:
            return ""
        if root in resolved.parents:
            # Only prefer the cwd-relative reading when it actually exists on
            # disk; otherwise the argument is already repo-relative.
            if resolved.exists() or raw.is_absolute():
                return resolved.relative_to(root).as_posix()
        elif raw.is_absolute():
            raise GitRefError(f"path is outside the repository: {path}")

    text = str(raw).strip()
    while text.startswith("./"):
        text = text[2:]
    text = text.strip("/")
    if text in ("", "."):
        return ""
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise GitRefError(f"path must not escape the repository root: {path}")
    return "/".join(parts)


def join_repo_path(base: str, extra: str | None) -> str:
    """Join a sub-path onto an asset path, refusing to escape *base*."""
    if not extra:
        return base
    sub = normalize_repo_path(extra)
    if not sub:
        return base
    return f"{base}/{sub}" if base else sub


# ---------------------------------------------------------------------------
# object resolution
# ---------------------------------------------------------------------------


def head_commit(repo_root: str | Path) -> str:
    """Return the full SHA of HEAD."""
    return _git_text(["rev-parse", "HEAD"], repo_root)


def resolve_commit(repo_root: str | Path, commit: str) -> str:
    """Return the full SHA for *commit*.

    Raises
    ------
    MissingCommit
        When the revision does not resolve to a commit in this clone.

    """
    try:
        return _git_text(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"], repo_root)
    except GitRefError as exc:
        raise MissingCommit(f"commit not found in this repository: {commit}") from exc


def _spec(commit: str, path: str) -> str:
    return f"{commit}:{path}" if path else f"{commit}^{{tree}}"


def object_kind(repo_root: str | Path, commit: str, path: str) -> str:
    """Return ``"blob"``/``"tree"``/``"commit"`` for ``<commit>:<path>``.

    Raises :class:`MissingCommit` when the commit is absent and
    :class:`MissingPath` when the path is absent at that commit.
    """
    if not _git_ok(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"], repo_root):
        raise MissingCommit(f"commit not found in this repository: {commit}")
    try:
        return _git_text(["cat-file", "-t", _spec(commit, path)], repo_root)
    except GitRefError as exc:
        raise MissingPath(f"path not found at {commit[:12]}: {path or '.'}") from exc


def read_blob(repo_root: str | Path, commit: str, path: str) -> bytes:
    """Return the bytes of the blob at ``<commit>:<path>``."""
    kind = object_kind(repo_root, commit, path)
    if kind != "blob":
        raise GitRefError(f"not a file at {commit[:12]}: {path or '.'} is a {kind}")
    return _git_bytes(["cat-file", "blob", _spec(commit, path)], repo_root)


def list_tree(repo_root: str | Path, commit: str, path: str) -> list[TreeEntry]:
    """Return the direct entries of the tree at ``<commit>:<path>``."""
    kind = object_kind(repo_root, commit, path)
    if kind != "tree":
        raise GitRefError(f"not a directory at {commit[:12]}: {path or '.'} is a {kind}")
    raw = _git_bytes(["ls-tree", "-l", "-z", _spec(commit, path)], repo_root)
    entries: list[TreeEntry] = []
    for chunk in raw.split(b"\0"):
        if not chunk:
            continue
        head, _, name = chunk.partition(b"\t")
        fields = head.split()
        if len(fields) < 3:
            continue
        mode = fields[0].decode("utf-8", "replace")
        etype = fields[1].decode("utf-8", "replace")
        oid = fields[2].decode("utf-8", "replace")
        size_raw = fields[3].decode("utf-8", "replace") if len(fields) > 3 else "-"
        entry_name = name.decode("utf-8", "surrogateescape")
        entries.append(
            TreeEntry(
                name=entry_name,
                path=f"{path}/{entry_name}" if path else entry_name,
                kind=etype,
                mode=mode,
                oid=oid,
                size=int(size_raw) if size_raw.isdigit() else None,
            )
        )
    entries.sort(key=lambda e: (e.kind != "tree", e.name))
    return entries


def blob_size(repo_root: str | Path, commit: str, path: str) -> int:
    """Return the size in bytes of the blob at ``<commit>:<path>``."""
    return int(_git_text(["cat-file", "-s", _spec(commit, path)], repo_root))


# ---------------------------------------------------------------------------
# push status
# ---------------------------------------------------------------------------


def has_remotes(repo_root: str | Path) -> bool:
    """Return True when the repository has at least one configured remote."""
    try:
        return bool(_git_text(["remote"], repo_root))
    except GitRefError:  # pragma: no cover - defensive
        return False


def remote_refs_containing(repo_root: str | Path, commit: str) -> list[str]:
    """Return remote-tracking refs that contain *commit* (possibly empty)."""
    try:
        raw = _git_text(["branch", "-r", "--contains", commit], repo_root)
    except GitRefError:
        return []
    return [line.strip().lstrip("* ").strip() for line in raw.splitlines() if line.strip()]


def unpushed_warning(repo_root: str | Path, commit: str) -> str | None:
    """Return a human-readable warning when *commit* is not on any remote.

    An asset is only shareable if the commit it points at is reachable from
    the clone the reader has. This never blocks a write — the design doc's
    position is "warn, do not guarantee".
    """
    short = commit[:12]
    if not has_remotes(repo_root):
        return (
            f"commit {short} lives in a repository with no remote: "
            "this asset reference will not resolve for anyone else until you add a "
            "remote and push."
        )
    if not remote_refs_containing(repo_root, commit):
        return (
            f"commit {short} is not contained in any remote-tracking branch: "
            "push it, or this asset reference will be broken in other clones."
        )
    return None


# ---------------------------------------------------------------------------
# content type
# ---------------------------------------------------------------------------

_EXTRA_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".py": "text/x-python; charset=utf-8",
    ".ts": "text/plain; charset=utf-8",
    ".tsx": "text/plain; charset=utf-8",
    ".jsonl": "application/x-ndjson",
    ".toml": "text/plain; charset=utf-8",
    ".rs": "text/plain; charset=utf-8",
    ".cu": "text/plain; charset=utf-8",
}


def guess_content_type(path: str) -> str:
    """Best-effort content type from a filename (never raises)."""
    suffix = Path(path).suffix.lower()
    if suffix in _EXTRA_TYPES:
        return _EXTRA_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(path)
    if guessed:
        if guessed.startswith("text/") and "charset" not in guessed:
            return f"{guessed}; charset=utf-8"
        return guessed
    return "application/octet-stream"
