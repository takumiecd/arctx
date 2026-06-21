"""Payload records attached to nodes or steps.

A target may have multiple payloads attached.
Payloads are immutable and append-only; CutPayload encodes cuts
without ever deleting graph records.

Built-in payload types defined here (core):
  - NodePayload: generic node payload with type + content dict
  - StepPayload: generic step payload with type + content dict
  - CutPayload: append-only inactivity marker (node or step)

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
class AssetPayload(PayloadBase):
    """A file asset (image, video, document, …) attached to a Node or Step.

    The file itself lives under ``<run_dir>/artifacts/`` and is referenced by
    the run-relative ``path``. Asset visibility (which records may reference an
    asset by URL) is computed from the DAG at read time in
    :mod:`arctx.core.lineage`: an asset is reachable from the record it is
    attached to and that record's descendants.
    """

    payload_id: str
    target_id: str
    target_kind: Literal["node", "step"]

    asset_id: str          # Unique id of the asset (e.g. ast_<uuid>)
    filename: str          # Original filename
    mime_type: str         # MIME type (e.g. image/png)
    size_bytes: int        # File size in bytes
    path: str              # Run-relative path (e.g. artifacts/<asset_id>_filename)

    metadata: dict[str, JSONValue] = field(default_factory=dict)
    payload_type: str = field(default="asset", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Payload union type (core only — extensions extend via registration)
# ---------------------------------------------------------------------------

Payload = NodePayload | StepPayload | CutPayload | AssetPayload


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


def _asset_from_dict(data: dict[str, JSONValue]) -> AssetPayload:
    return AssetPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        target_kind=data["target_kind"],  # type: ignore[arg-type]
        asset_id=str(data["asset_id"]),
        filename=str(data["filename"]),
        mime_type=str(data["mime_type"]),
        size_bytes=int(data["size_bytes"]),  # type: ignore[arg-type]
        path=str(data["path"]),
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
register_payload_class(AssetPayload)

register_payload_decoder("node_payload", _node_payload_from_dict)
register_payload_decoder("step_payload", _step_payload_from_dict)
register_payload_decoder("cut", _cut_from_dict)
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
