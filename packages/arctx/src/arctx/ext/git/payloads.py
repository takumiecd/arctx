"""Git-related payload records.

These payloads are part of the git extension and are registered with the core
payload deserialization system at import time via register_payload_class and
register_payload_decoder.

Classes:
  - CommitEntry: a single commit entry in a GitChangePayload
  - DiffSummary: aggregate diff stats
  - GitChangePayload: git commit/diff record on a Transition
  - BranchPayload: branch where a transition was created
  - RevertPayload: marks a transition as a revert
  - CherryPickPayload: marks a transition as a cherry-pick
  - MergePayload: marks a transition as a git merge
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from arctx.core.schema.payloads import (
    PayloadBase,
    register_payload_class,
    register_payload_decoder,
)
from arctx.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class CommitEntry:
    """A single commit entry in a GitChangePayload commit_log."""

    sha: str
    subject: str
    author: str
    date: str  # ISO 8601 with timezone

    def to_dict(self) -> dict[str, str]:
        return {"sha": self.sha, "subject": self.subject, "author": self.author, "date": self.date}


@dataclass(frozen=True)
class DiffSummary:
    """Aggregate diff stats from git --shortstat."""

    files_changed: int
    insertions: int
    deletions: int

    def to_dict(self) -> dict[str, int]:
        return {
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions,
        }


@dataclass(frozen=True)
class RemoteRef:
    """One git remote in a repo registry entry.

    A repo commonly exposes the same upstream as several URL forms (ssh vs
    https). All known forms are kept so resolution can match on any of them;
    ``canonical`` on the owning ``RepoPayload`` is the normalized key derived
    from these.
    """

    kind: str  # "ssh" | "https" | "git" | ...
    url: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "url": self.url}


@dataclass(frozen=True)
class RepoPayload(PayloadBase):
    """Registry entry mapping one git repo into the run (the repo 対応表).

    Run-scoped: attached to the run root node. git payloads reference a repo
    by ``repo_id`` only; this entry is the single source of truth for what
    that repo is.

    Identity (shared, environment-independent): ``repo_id`` (opaque primary
    key), ``slug`` (USER/REPO display name), ``remotes`` (all known URL forms),
    ``canonical`` (normalized key for same-repo matching).

    ``local_path`` is this machine's checkout location. It is environment
    specific and MUST be stripped before the run leaves this machine (export /
    hub push); see ``to_shareable``.
    """

    payload_id: str
    target_id: str
    repo_id: str
    slug: str | None = None
    remotes: tuple[RemoteRef, ...] = ()
    canonical: str | None = None
    local_path: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["node"] = field(default="node", init=False)
    payload_type: str = field(default="repo", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "repo_id": self.repo_id,
            "slug": self.slug,
            "remotes": [r.to_dict() for r in self.remotes],
            "canonical": self.canonical,
            "local_path": self.local_path,
            "metadata": dict(self.metadata),
        }

    def shareable(self) -> "RepoPayload":
        """Return a copy with environment-specific fields stripped."""
        return RepoPayload(
            payload_id=self.payload_id,
            target_id=self.target_id,
            repo_id=self.repo_id,
            slug=self.slug,
            remotes=self.remotes,
            canonical=self.canonical,
            local_path=None,
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class BranchPayload(PayloadBase):
    """Branch where a transition was created. Historical, immutable.

    Attached to a Transition at commit time. Records the git branch name
    on which the transition originated. Not updated on merge/rebase.
    """

    payload_id: str
    target_id: str
    branch: str
    repo_id: str = ""
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="branch", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "branch": self.branch,
            "repo_id": self.repo_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GitChangePayload(PayloadBase):
    """Git repository change information attached to a Transition."""

    payload_id: str
    target_id: str
    branch: str
    head_commit: str
    diff_summary: DiffSummary = field(
        default_factory=lambda: DiffSummary(files_changed=0, insertions=0, deletions=0)
    )
    commit_log: tuple[CommitEntry, ...] = ()
    repo_id: str = ""
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="git_change", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "branch": self.branch,
            "head_commit": self.head_commit,
            "diff_summary": self.diff_summary.to_dict(),
            "commit_log": [c.to_dict() for c in self.commit_log],
            "repo_id": self.repo_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RevertPayload(PayloadBase):
    """Marks a transition as a revert of another transition.

    Attached to the *new* (forward) transition that undoes the original commit.
    The reverted transition is NOT touched; no CutPayload is appended to it.
    """

    payload_id: str
    target_id: str
    reverted_transition: str  # original t_id whose effect is undone
    reverted_commit: str      # original sha that was reverted
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="revert", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "reverted_transition": self.reverted_transition,
            "reverted_commit": self.reverted_commit,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CherryPickPayload(PayloadBase):
    """Marks a transition as a cherry-pick of another transition / commit."""

    payload_id: str
    target_id: str
    source_transition: str | None  # may be None if cross-repo or not found
    source_commit: str
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="cherry_pick", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "source_transition": self.source_transition,
            "source_commit": self.source_commit,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MergePayload(PayloadBase):
    """Marks a transition as a git merge (multi-input, with common ancestor).

    Attached to the new Transition that represents the merge commit.
    Input node IDs are (current_tip, other_tip); the transition has 2+ inputs.
    """

    payload_id: str
    target_id: str
    merged_from: str   # branch name or node id of the merged-in branch
    merged_into: str   # branch name or node id of the target (current) branch
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="merge", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "merged_from": self.merged_from,
            "merged_into": self.merged_into,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Decoder functions
# ---------------------------------------------------------------------------


def _git_change_from_dict(data: dict[str, JSONValue]) -> GitChangePayload:
    raw_log = data.get("commit_log") or []
    commit_log = tuple(
        CommitEntry(
            sha=str(e["sha"]),
            subject=str(e["subject"]),
            author=str(e["author"]),
            date=str(e["date"]),
        )
        for e in raw_log
    )
    raw_summary = data.get("diff_summary") or {}
    diff_summary = DiffSummary(
        files_changed=int(raw_summary.get("files_changed", 0)),
        insertions=int(raw_summary.get("insertions", 0)),
        deletions=int(raw_summary.get("deletions", 0)),
    )
    return GitChangePayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        branch=str(data.get("branch", "")),
        head_commit=str(data.get("head_commit", "")),
        diff_summary=diff_summary,
        commit_log=commit_log,
        repo_id=str(data.get("repo_id", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def _branch_payload_from_dict(data: dict[str, JSONValue]) -> BranchPayload:
    return BranchPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        branch=str(data.get("branch", "")),
        repo_id=str(data.get("repo_id", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def _repo_payload_from_dict(data: dict[str, JSONValue]) -> RepoPayload:
    raw_remotes = data.get("remotes") or []
    remotes = tuple(
        RemoteRef(kind=str(r.get("kind", "")), url=str(r.get("url", "")))
        for r in raw_remotes
    )
    raw_slug = data.get("slug")
    raw_canonical = data.get("canonical")
    raw_local = data.get("local_path")
    return RepoPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        repo_id=str(data["repo_id"]),
        slug=str(raw_slug) if raw_slug is not None else None,
        remotes=remotes,
        canonical=str(raw_canonical) if raw_canonical is not None else None,
        local_path=str(raw_local) if raw_local is not None else None,
        metadata=dict(data.get("metadata") or {}),
    )


def _revert_from_dict(data: dict[str, JSONValue]) -> RevertPayload:
    return RevertPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        reverted_transition=str(data.get("reverted_transition", "")),
        reverted_commit=str(data.get("reverted_commit", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def _cherry_pick_from_dict(data: dict[str, JSONValue]) -> CherryPickPayload:
    raw_source_transition = data.get("source_transition")
    source_transition = str(raw_source_transition) if raw_source_transition is not None else None
    return CherryPickPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        source_transition=source_transition,
        source_commit=str(data.get("source_commit", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def _merge_from_dict(data: dict[str, JSONValue]) -> MergePayload:
    return MergePayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        merged_from=str(data.get("merged_from", "")),
        merged_into=str(data.get("merged_into", "")),
        metadata=dict(data.get("metadata") or {}),
    )


# ---------------------------------------------------------------------------
# Register with core dispatch system (import-time side effect).
# ---------------------------------------------------------------------------

register_payload_class(GitChangePayload)
register_payload_class(BranchPayload)
register_payload_class(RepoPayload)
register_payload_class(RevertPayload)
register_payload_class(CherryPickPayload)
register_payload_class(MergePayload)

register_payload_decoder("git_change", _git_change_from_dict)
register_payload_decoder("branch", _branch_payload_from_dict)
register_payload_decoder("repo", _repo_payload_from_dict)
register_payload_decoder("revert", _revert_from_dict)
register_payload_decoder("cherry_pick", _cherry_pick_from_dict)
register_payload_decoder("merge", _merge_from_dict)
