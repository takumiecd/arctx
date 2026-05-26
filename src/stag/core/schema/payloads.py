"""Payload records attached to nodes or transitions.

A target may have multiple payloads attached.
Payloads are immutable and append-only; CutPayload encodes cuts
without ever deleting graph records.

Built-in payload types:
  - NodePayload: generic node payload with type + content dict
  - TransitionPayload: generic transition payload with type + content dict
  - CutPayload: append-only inactivity marker (node or transition)
  - GitChangePayload: git commit/diff record (transition only)

Users can register custom PayloadBase subclasses with register_payload_class().
Unknown payload_type values fall back to the appropriate generic class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Union

from stag.core.types import JSONValue, to_jsonable


class PayloadBase(ABC):
    """Common contract for payload records attached to graph targets."""

    payload_id: str
    target_id: str
    target_kind: Literal["node", "transition"]
    payload_type: str

    @abstractmethod
    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-serializable representation."""


# ---------------------------------------------------------------------------
# Generic payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodePayload(PayloadBase):
    """Generic node payload. Use the ``type`` field to distinguish purposes."""

    payload_id: str
    target_id: str
    type: str
    content: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["node"] = field(default="node", init=False)
    payload_type: str = field(default="node_payload", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class TransitionPayload(PayloadBase):
    """Generic transition payload. Use the ``type`` field to distinguish purposes."""

    payload_id: str
    target_id: str
    type: str
    content: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="transition_payload", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Built-in typed payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CutPayload(PayloadBase):
    """Append-only cut marker on a Node or Transition.

    Inactivity is computed at read time; graph records are never deleted.
    """

    payload_id: str
    target_id: str
    target_kind: Literal["node", "transition"]
    reason: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    payload_type: str = field(default="cut", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


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
class BranchPayload(PayloadBase):
    """Branch where a transition was created. Historical, immutable.

    Attached to a Transition at commit time. Records the git branch name
    on which the transition originated. Not updated on merge/rebase.
    """

    payload_id: str
    target_id: str
    branch: str
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


@dataclass(frozen=True)
class JoinPayload(PayloadBase):
    """Marks a transition as a stag-only join (multi-input, NO common ancestor).

    Used to integrate independent DAGs that don't share a git history.
    Unlike MergePayload, there is no corresponding git merge commit required.
    """

    payload_id: str
    target_id: str
    joined_views: tuple[str, ...]  # branch or view names being joined
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="join", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "joined_views": list(self.joined_views),
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Payload union type (for type annotations)
# ---------------------------------------------------------------------------

Payload = Union[
    NodePayload,
    TransitionPayload,
    CutPayload,
    GitChangePayload,
    BranchPayload,
    RevertPayload,
    CherryPickPayload,
    MergePayload,
    JoinPayload,
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PAYLOAD_REGISTRY: dict[str, type[PayloadBase]] = {}


def register_payload_class(cls: type[PayloadBase]) -> None:
    """Register a custom PayloadBase subclass for deserialization dispatch.

    The class must have a ``payload_type`` class-level attribute (a string).
    Call this once at import time before loading any runs.

    Example::

        @dataclass(frozen=True)
        class ExperimentResultPayload(PayloadBase):
            ...
            payload_type: str = field(default="experiment_result", init=False)

        register_payload_class(ExperimentResultPayload)
    """
    # Instantiate a sentinel to read payload_type — use a class-level attribute if available.
    pt = getattr(cls, "payload_type", None)
    if pt is None:
        raise ValueError(f"{cls.__name__} must have a payload_type class attribute")
    _PAYLOAD_REGISTRY[pt] = cls


# Register built-ins.
register_payload_class(NodePayload)
register_payload_class(TransitionPayload)
register_payload_class(CutPayload)
register_payload_class(GitChangePayload)
register_payload_class(BranchPayload)
register_payload_class(RevertPayload)
register_payload_class(CherryPickPayload)
register_payload_class(MergePayload)
register_payload_class(JoinPayload)


# ---------------------------------------------------------------------------
# Deserialization
# ---------------------------------------------------------------------------


def payload_from_dict(data: dict[str, JSONValue]) -> PayloadBase:
    """Reconstruct a PayloadBase subclass from its JSON dict form.

    Dispatches by ``payload_type``. Falls back to NodePayload / TransitionPayload
    for unknown types (preserving original payload_type as ``type`` and
    original data as ``content``).
    """
    payload_type = data.get("payload_type")
    cls = _PAYLOAD_REGISTRY.get(str(payload_type)) if payload_type is not None else None

    if cls is NodePayload:
        return _node_payload_from_dict(data)
    if cls is TransitionPayload:
        return _transition_payload_from_dict(data)
    if cls is CutPayload:
        return _cut_from_dict(data)
    if cls is GitChangePayload:
        return _git_change_from_dict(data)
    if cls is BranchPayload:
        return _branch_payload_from_dict(data)
    if cls is RevertPayload:
        return _revert_from_dict(data)
    if cls is CherryPickPayload:
        return _cherry_pick_from_dict(data)
    if cls is MergePayload:
        return _merge_from_dict(data)
    if cls is JoinPayload:
        return _join_from_dict(data)
    if cls is not None:
        # Custom registered class — try constructor with all fields.
        return _generic_custom_from_dict(cls, data)

    # Unknown payload_type: fall back to generic based on target_kind.
    target_kind = data.get("target_kind", "node")
    if target_kind == "transition":
        return TransitionPayload(
            payload_id=str(data.get("payload_id", "")),
            target_id=str(data.get("target_id", "")),
            type=str(payload_type or "unknown"),
            content={k: v for k, v in data.items() if k not in ("payload_id", "target_id", "target_kind", "payload_type", "type", "content", "metadata")},
            metadata=dict(data.get("metadata") or {}),
        )
    return NodePayload(
        payload_id=str(data.get("payload_id", "")),
        target_id=str(data.get("target_id", "")),
        type=str(payload_type or "unknown"),
        content={k: v for k, v in data.items() if k not in ("payload_id", "target_id", "target_kind", "payload_type", "type", "content", "metadata")},
        metadata=dict(data.get("metadata") or {}),
    )


def _node_payload_from_dict(data: dict[str, JSONValue]) -> NodePayload:
    return NodePayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        type=str(data.get("type", "")),
        content=dict(data.get("content") or {}),
        metadata=dict(data.get("metadata") or {}),
    )


def _transition_payload_from_dict(data: dict[str, JSONValue]) -> TransitionPayload:
    return TransitionPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        type=str(data.get("type", "")),
        content=dict(data.get("content") or {}),
        metadata=dict(data.get("metadata") or {}),
    )


def _cut_from_dict(data: dict[str, JSONValue]) -> CutPayload:
    return CutPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        target_kind=data["target_kind"],  # type: ignore[arg-type]
        reason=data.get("reason"),
        metadata=dict(data.get("metadata") or {}),
    )


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


def _join_from_dict(data: dict[str, JSONValue]) -> JoinPayload:
    raw_views = data.get("joined_views") or []
    joined_views = tuple(str(v) for v in raw_views)
    return JoinPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        joined_views=joined_views,
        metadata=dict(data.get("metadata") or {}),
    )


def _generic_custom_from_dict(cls: type[PayloadBase], data: dict[str, JSONValue]) -> PayloadBase:
    """Best-effort reconstruction for user-registered subclasses."""
    import dataclasses
    if dataclasses.is_dataclass(cls):
        fields = {f.name for f in dataclasses.fields(cls) if f.init}  # type: ignore[arg-type]
        kwargs = {k: v for k, v in data.items() if k in fields}
        try:
            return cls(**kwargs)  # type: ignore[return-value]
        except Exception:
            pass
    # Fallback: generic node or transition payload.
    return payload_from_dict({**data, "payload_type": None})
