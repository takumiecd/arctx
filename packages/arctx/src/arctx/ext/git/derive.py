"""Read-time derivation of everything a ``GitChangePayload`` does not store.

"jsonl は事実、見た目は導出" — a :class:`~arctx.ext.git.payloads.GitChangePayload`
records commit hashes and a branch. The subjects, authors, dates, file lists,
diff stats, and patch text that surfaces display are read back out of git here,
on demand.

Deriving instead of baking means a record can never disagree with the
repository. The cost is that a clone missing the commit (shallow clone, commit
never pushed) has nothing to show — so every derivation degrades to an explicit
:data:`MISSING_COMMIT_NOTE` marker rather than failing, and callers render the
marker instead of stale text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from arctx.core.gitref import (
    CommitInfo,
    DiffStat,
    GitRefError,
    changed_files,
    commit_infos,
    commit_patch,
    diff_stat,
    repo_root_for,
)
from arctx.ext.git.payloads import GitChangePayload

__all__ = [
    "ARCTX_DATA_EXCLUDE",
    "MISSING_COMMIT_NOTE",
    "NO_REPOSITORY_NOTE",
    "DerivedGitChange",
    "derive_git_change",
]

MISSING_COMMIT_NOTE = "(commit not available locally)"
NO_REPOSITORY_NOTE = "(no git repository available here)"

# Run data lives in `.arctx/` inside the repository, and recording commit N
# necessarily lands in commit N+1 ("one commit behind" is the spec). Counting
# that bookkeeping as part of the change under review would make every diff
# look noisy, so it is excluded here — the same exclusion `git verify` uses to
# decide the tree is clean.
ARCTX_DATA_EXCLUDE = (".arctx/**",)


@dataclass(frozen=True)
class DerivedGitChange:
    """What a ``GitChangePayload`` looks like once git has been consulted."""

    head_commit: str
    branch: str
    commits: tuple[str, ...]
    available: bool
    note: str | None = None
    commit_log: tuple[CommitInfo, ...] = ()
    diff_stat: DiffStat = field(default_factory=DiffStat)
    files: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return {
            "head_commit": self.head_commit,
            "branch": self.branch,
            "commits": list(self.commits),
            "available": self.available,
            "note": self.note,
            "commit_log": [entry.to_dict() for entry in self.commit_log],
            "diff_stat": self.diff_stat.to_dict(),
            "files": list(self.files),
        }

    def summary_line(self) -> str:
        """Return a one-line human rendering, or the unavailability marker."""
        if not self.available:
            return f"{self.head_commit[:12]} {self.note or MISSING_COMMIT_NOTE}".strip()
        stat = self.diff_stat
        subject = self.commit_log[0].subject if self.commit_log else ""
        parts = [self.head_commit[:12]]
        if subject:
            parts.append(subject)
        parts.append(
            f"({stat.files_changed} files, +{stat.insertions}/-{stat.deletions})"
        )
        return " ".join(parts)


def _unavailable(payload: GitChangePayload, note: str) -> DerivedGitChange:
    return DerivedGitChange(
        head_commit=payload.head_commit,
        branch=payload.branch,
        commits=payload.commit_shas,
        available=False,
        note=note,
    )


def derive_git_change(
    payload: GitChangePayload,
    repo_root: str | Path | None = None,
) -> DerivedGitChange:
    """Derive the displayable view of *payload* from the repository.

    *repo_root* defaults to the repository enclosing the current directory
    ("absent = self": a run's git records always refer to the repo holding the
    run data). Never raises — an unresolvable reference comes back with
    ``available=False`` and an explanatory ``note``.
    """
    if not payload.head_commit:
        return _unavailable(payload, MISSING_COMMIT_NOTE)

    try:
        root = Path(repo_root) if repo_root is not None else repo_root_for()
    except GitRefError:
        return _unavailable(payload, NO_REPOSITORY_NOTE)

    base = payload.base_commit
    try:
        stat = diff_stat(root, payload.head_commit, base, exclude=ARCTX_DATA_EXCLUDE)
        files = tuple(
            changed_files(root, payload.head_commit, base, exclude=ARCTX_DATA_EXCLUDE)
        )
    except GitRefError:
        return _unavailable(payload, MISSING_COMMIT_NOTE)

    return DerivedGitChange(
        head_commit=payload.head_commit,
        branch=payload.branch,
        commits=payload.commit_shas,
        available=True,
        commit_log=tuple(commit_infos(root, payload.commit_shas)),
        diff_stat=stat,
        files=files,
    )


def derive_patch(
    payload: GitChangePayload,
    repo_root: str | Path | None = None,
    *,
    max_bytes: int = 300_000,
) -> tuple[str, bool, int, str | None]:
    """Return ``(text, truncated, byte_count, note)`` for *payload*'s diff.

    ``note`` is non-``None`` exactly when the patch could not be derived, and
    is the marker a surface should render in place of the diff.
    """
    if not payload.head_commit:
        return "", False, 0, MISSING_COMMIT_NOTE
    try:
        root = Path(repo_root) if repo_root is not None else repo_root_for()
    except GitRefError:
        return "", False, 0, NO_REPOSITORY_NOTE
    try:
        text, truncated, byte_count = commit_patch(
            root,
            payload.head_commit,
            payload.base_commit,
            max_bytes=max_bytes,
            exclude=ARCTX_DATA_EXCLUDE,
        )
    except GitRefError:
        return "", False, 0, MISSING_COMMIT_NOTE
    return text, truncated, byte_count, None
