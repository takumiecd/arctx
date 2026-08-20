"""Payload records attached to nodes or steps.

A target may have multiple payloads attached.
Payloads are immutable and append-only; CutPayload encodes cuts
without ever deleting graph records.

Built-in payload types defined here (core):
  - NodePayload: generic node payload with type + content dict
  - StepPayload: generic step payload with type + content dict
  - CutPayload: append-only inactivity marker (node or step)
  - SummaryPayload: descriptive context snapshot on a node (history truncation)
  - AssetPayload: reference to a git object, ``(commit, path)``

Extension-specific payload classes (e.g. GitChangePayload, BranchPayload,
RevertPayload, CherryPickPayload, MergePayload) live with their owning
extension and register themselves via ``register_payload_class`` and
``register_payload_decoder`` at import time.

Users can register custom PayloadBase subclasses with register_payload_class()
and supply a decoder via register_payload_decoder(). Unknown payload_type
values fall back to the appropriate generic class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from arctx.core.types import JSONValue, to_jsonable


class PayloadBase(ABC):
    """Common contract for payload records attached to graph targets."""

    payload_id: str
    target_id: str
    target_kind: Literal["node", "step"]
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
class StepPayload(PayloadBase):
    """Generic step payload. Use the ``type`` field to distinguish purposes."""

    payload_id: str
    target_id: str
    type: str
    content: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["step"] = field(default="step", init=False)
    payload_type: str = field(default="step_payload", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Built-in typed payloads (core)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CutPayload(PayloadBase):
    """Append-only cut marker on a Node or Step.

    Inactivity is computed at read time; graph records are never deleted.
    """

    payload_id: str
    target_id: str
    target_kind: Literal["node", "step"]
    reason: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    payload_type: str = field(default="cut", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class UncutPayload(PayloadBase):
    """Append-only reversal of a cut on the same Node or Step.

    Cuts are never deleted. An UncutPayload supersedes the most recent
    CutPayload on its target: effective cut state is computed at read time as
    "the last cut/uncut marker wins" (see :mod:`arctx.core.cuts`). A target can
    be cut, uncut, then cut again — the full sequence stays recorded.
    """

    payload_id: str
    target_id: str
    target_kind: Literal["node", "step"]
    reason: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    payload_type: str = field(default="uncut", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class JoinPayload(PayloadBase):
    """Step-targeting marker for a multi-input step that joins independent histories."""

    payload_id: str
    target_id: str
    joined_views: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["step"] = field(default="step", init=False)
    payload_type: str = field(default="join", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class AssetPayload(PayloadBase):
    """A reference to a git object: ``(commit, path)``.

    ARCTX never copies asset bytes. An asset names a commit and a
    repo-root-relative path, which may be a **file or a directory** (git has
    trees, so both are addressable). The bytes are resolved at read time by the
    serve layer via ``git cat-file`` / ``git ls-tree``.

    Per the git-native "absent = self" convention there is no repo field: the
    repository is the one enclosing the run data. Nothing derivable is stored —
    no size, no mime type, no content hash — those come from git.

    Target may be a Node (an artifact of the state reached) or a Step (an
    artifact of the transition). ``title`` is an optional human label.

    This record is deliberately free of git imports; resolution helpers live in
    :mod:`arctx.core.gitref`.
    """

    payload_id: str
    target_id: str
    target_kind: Literal["node", "step"]
    commit: str
    path: str
    title: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    payload_type: str = field(default="asset", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class SummaryPayload(PayloadBase):
    """A context snapshot attached to a Node for history truncation / hand-off.

    Descriptive and monotonic: attaching a summary never changes the validity of
    the node or its descendants (unlike :class:`CutPayload`). It only lets a
    reader collapse history — ``RunHandle.trace(..., stop_at_summary=True)``
    stops the backward walk at the nearest node carrying a summary, yielding
    "nearest summary + steps below it" instead of the full history.

    Node-targeting only: a summary describes the state reached at a node.

    ``text`` is rendered according to ``metadata["format"]`` when present.
    Supported GUI formats are ``"markdown"`` (default), ``"html"`` (sanitized),
    and ``"text"``. Closing summaries and hand-off notes should be complete
    enough to read as the conclusion for a collapsed lane.
    """

    payload_id: str
    target_id: str
    text: str
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["node"] = field(default="node", init=False)
    payload_type: str = field(default="summary", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Payload union type (core only — extensions extend via registration)
# ---------------------------------------------------------------------------

Payload = (
    NodePayload
    | StepPayload
    | CutPayload
    | UncutPayload
    | JoinPayload
    | SummaryPayload
    | AssetPayload
)


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

_PAYLOAD_REGISTRY: dict[str, type[PayloadBase]] = {}
_PAYLOAD_DECODERS: dict[str, Callable[[dict[str, JSONValue]], PayloadBase]] = {}


def register_payload_class(cls: type[PayloadBase]) -> None:
    """Register a PayloadBase subclass for deserialization dispatch.

    The class must have a ``payload_type`` class-level attribute (a string).
    Call this once at import time (typically from an extension module).
    """
    pt = getattr(cls, "payload_type", None)
    if pt is None:
        raise ValueError(f"{cls.__name__} must have a payload_type class attribute")
    _PAYLOAD_REGISTRY[pt] = cls


def register_payload_decoder(
    payload_type: str,
    decoder: Callable[[dict[str, JSONValue]], PayloadBase],
) -> None:
    """Register a custom decoder function for a payload_type.

    Decoders take precedence over the registered class lookup in
    ``payload_from_dict``. Use this when the JSON shape needs custom
    reconstruction logic (e.g. nested dataclasses like CommitEntry).
    """
    _PAYLOAD_DECODERS[payload_type] = decoder


def registered_payload_types() -> tuple[str, ...]:
    """Sorted names of every payload_type this process can deserialize.

    This is the process's decode capability, used as a cache fingerprint: a
    RunGraph decoded by a process with a different registry (an older install,
    or one without an extension's schema imported) is not interchangeable —
    unknown types degrade to generic payloads and would poison a shared cache.
    """
    return tuple(sorted(set(_PAYLOAD_REGISTRY) | set(_PAYLOAD_DECODERS)))


def _node_payload_from_dict(data: dict[str, JSONValue]) -> NodePayload:
    return NodePayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        type=str(data.get("type", "")),
        content=dict(data.get("content") or {}),
        metadata=dict(data.get("metadata") or {}),
    )


def _step_payload_from_dict(data: dict[str, JSONValue]) -> StepPayload:
    return StepPayload(
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
        reason=data.get("reason"),  # type: ignore[arg-type]
        metadata=dict(data.get("metadata") or {}),
    )


def _uncut_from_dict(data: dict[str, JSONValue]) -> UncutPayload:
    return UncutPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        target_kind=data["target_kind"],  # type: ignore[arg-type]
        reason=data.get("reason"),  # type: ignore[arg-type]
        metadata=dict(data.get("metadata") or {}),
    )


def _summary_from_dict(data: dict[str, JSONValue]) -> SummaryPayload:
    return SummaryPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        text=str(data.get("text", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def _asset_from_dict(data: dict[str, JSONValue]) -> AssetPayload:
    title = data.get("title")
    return AssetPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        target_kind=data.get("target_kind", "node"),  # type: ignore[arg-type]
        commit=str(data.get("commit", "")),
        path=str(data.get("path", "")),
        title=str(title) if title is not None else None,
        metadata=dict(data.get("metadata") or {}),
    )


def _join_from_dict(data: dict[str, JSONValue]) -> JoinPayload:
    return JoinPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        joined_views=tuple(str(x) for x in data.get("joined_views", ())),
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
    return payload_from_dict({**data, "payload_type": None})


# Register core built-ins.
register_payload_class(NodePayload)
register_payload_class(StepPayload)
register_payload_class(CutPayload)
register_payload_class(UncutPayload)
register_payload_class(SummaryPayload)
register_payload_class(JoinPayload)
register_payload_class(AssetPayload)

register_payload_decoder("node_payload", _node_payload_from_dict)
register_payload_decoder("step_payload", _step_payload_from_dict)
register_payload_decoder("cut", _cut_from_dict)
register_payload_decoder("uncut", _uncut_from_dict)
register_payload_decoder("summary", _summary_from_dict)
register_payload_decoder("join", _join_from_dict)
register_payload_decoder("asset", _asset_from_dict)


# ---------------------------------------------------------------------------
# Deserialization
# ---------------------------------------------------------------------------


def payload_from_dict(data: dict[str, JSONValue]) -> PayloadBase:
    """Reconstruct a PayloadBase subclass from its JSON dict form.

    Dispatch order:
      1. Custom decoder registered via register_payload_decoder.
      2. Registered class (via register_payload_class) — best-effort
         constructor invocation through _generic_custom_from_dict.
      3. Generic NodePayload / StepPayload fallback (unknown type).
    """
    payload_type = data.get("payload_type")
    pt_str = str(payload_type) if payload_type is not None else ""

    decoder = _PAYLOAD_DECODERS.get(pt_str) if pt_str else None
    if decoder is not None:
        return decoder(data)

    cls = _PAYLOAD_REGISTRY.get(pt_str) if pt_str else None
    if cls is not None:
        return _generic_custom_from_dict(cls, data)

    # Unknown payload_type: fall back to generic based on target_kind.
    target_kind = data.get("target_kind", "node")
    leftover = {
        k: v
        for k, v in data.items()
        if k not in (
            "payload_id",
            "target_id",
            "target_kind",
            "payload_type",
            "type",
            "content",
            "metadata",
        )
    }
    if target_kind == "step":
        return StepPayload(
            payload_id=str(data.get("payload_id", "")),
            target_id=str(data.get("target_id", "")),
            type=pt_str or "unknown",
            content=leftover,
            metadata=dict(data.get("metadata") or {}),
        )
    return NodePayload(
        payload_id=str(data.get("payload_id", "")),
        target_id=str(data.get("target_id", "")),
        type=pt_str or "unknown",
        content=leftover,
        metadata=dict(data.get("metadata") or {}),
    )
