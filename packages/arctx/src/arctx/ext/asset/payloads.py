"""Payload type for attached assets (images, videos, documents)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from arctx.core.schema.payloads import PayloadBase, register_payload_class, register_payload_decoder
from arctx.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class AssetPayload(PayloadBase):
    """Payload representing an attached file asset (image, video, document, etc.)."""

    payload_id: str
    target_id: str
    target_kind: Literal["node", "step"]

    asset_id: str          # Unique ID of the asset (e.g. ast_<uuid>)
    filename: str          # Original filename
    mime_type: str         # MIME type (e.g., image/png)
    size_bytes: int        # File size in bytes
    path: str              # Relative path inside run dir (e.g. artifacts/<asset_id>_filename)

    metadata: dict[str, JSONValue] = field(default_factory=dict)
    payload_type: str = field(default="asset", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-serializable representation of this asset payload."""
        return to_jsonable(self)  # type: ignore[return-value]


def _asset_payload_from_dict(data: dict[str, JSONValue]) -> AssetPayload:
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


# Register the schema
register_payload_class(AssetPayload)
register_payload_decoder("asset", _asset_payload_from_dict)
