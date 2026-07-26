"""Git-related payload records.

These payloads are part of the git extension and are registered with the core
payload deserialization system at import time via register_payload_class and
register_payload_decoder.

Classes:
  - GitChangePayload: git commit reference on a Step
  - BranchPayload: branch where a step was created
  - RevertPayload: marks a step as a revert
  - CherryPickPayload: marks a step as a cherry-pick
  - MergePayload: marks a step as a git merge

These records hold *facts* only — commit hashes and a branch name. Diff stats,
commit subjects, and patch text are derived from the repository at read time
(:mod:`arctx.core.gitref`, :mod:`arctx.ext.git.derive`), never baked in. This
module stays free of git imports.
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
class BranchPayload(PayloadBase):
    """Branch where a step was created. Historical, immutable.

    Attached to a Step at commit time. Records the git branch name
    on which the step originated. Not updated on merge/rebase.
    """

    payload_id: str
    target_id: str
    branch: str
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["step"] = field(default="step", init=False)
    payload_type: str = field(default="branch", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "branch": self.branch,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GitChangePayload(PayloadBase):
    """A reference to the git commits a Step produced.

    The record's truth is ``head_commit``, the optional full ``commits`` tuple
    (when a step spans several commits), and ``branch``. Everything a reader
    wants to *look at* — subjects, authors, dates, file lists, diff stats,
    patch text — is derived from the repository by
    :func:`arctx.ext.git.derive.derive_git_change`. If the commit is missing
    from a clone, surfaces render an explicit "commit not available locally"
    marker rather than showing stale baked text.
    """

    payload_id: str
    target_id: str
    branch: str
    head_commit: str
    commits: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["step"] = field(default="step", init=False)
    payload_type: str = field(default="git_change", init=False)

    @property
    def commit_shas(self) -> tuple[str, ...]:
        """Return every commit this record points at, oldest-first."""
        if self.commits:
            return self.commits
        return (self.head_commit,) if self.head_commit else ()

    @property
    def base_commit(self) -> str | None:
        """Return the recorded base commit, if the writer knew one."""
        base = self.metadata.get("base_commit")
        return str(base) if base else None

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "branch": self.branch,
            "head_commit": self.head_commit,
            "commits": list(self.commits),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RevertPayload(PayloadBase):
    """Marks a step as a revert of another step.

    Attached to the *new* (forward) step that undoes the original commit.
    The reverted step is NOT touched; no CutPayload is appended to it.
    """

    payload_id: str
    target_id: str
    reverted_step: str  # original t_id whose effect is undone
    reverted_commit: str      # original sha that was reverted
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["step"] = field(default="step", init=False)
    payload_type: str = field(default="revert", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "reverted_step": self.reverted_step,
            "reverted_commit": self.reverted_commit,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CherryPickPayload(PayloadBase):
    """Marks a step as a cherry-pick of another step / commit."""

    payload_id: str
    target_id: str
    source_step: str | None  # may be None if cross-repo or not found
    source_commit: str
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["step"] = field(default="step", init=False)
    payload_type: str = field(default="cherry_pick", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "source_step": self.source_step,
            "source_commit": self.source_commit,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MergePayload(PayloadBase):
    """Marks a step as a git merge (multi-input, with common ancestor).

    Attached to the new Step that represents the merge commit.
    Input node IDs are (current_tip, other_tip); the step has 2+ inputs.
    """

    payload_id: str
    target_id: str
    merged_from: str   # branch name or node id of the merged-in branch
    merged_into: str   # branch name or node id of the target (current) branch
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["step"] = field(default="step", init=False)
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
    return GitChangePayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        branch=str(data.get("branch", "")),
        head_commit=str(data.get("head_commit", "")),
        commits=tuple(str(sha) for sha in (data.get("commits") or [])),
        metadata=dict(data.get("metadata") or {}),
    )


def _branch_payload_from_dict(data: dict[str, JSONValue]) -> BranchPayload:
    return BranchPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        branch=str(data.get("branch", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def _revert_from_dict(data: dict[str, JSONValue]) -> RevertPayload:
    return RevertPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        reverted_step=str(data.get("reverted_step", "")),
        reverted_commit=str(data.get("reverted_commit", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def _cherry_pick_from_dict(data: dict[str, JSONValue]) -> CherryPickPayload:
    raw_source_step = data.get("source_step")
    source_step = str(raw_source_step) if raw_source_step is not None else None
    return CherryPickPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        source_step=source_step,
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
register_payload_class(RevertPayload)
register_payload_class(CherryPickPayload)
register_payload_class(MergePayload)

register_payload_decoder("git_change", _git_change_from_dict)
register_payload_decoder("branch", _branch_payload_from_dict)
register_payload_decoder("revert", _revert_from_dict)
register_payload_decoder("cherry_pick", _cherry_pick_from_dict)
register_payload_decoder("merge", _merge_from_dict)
