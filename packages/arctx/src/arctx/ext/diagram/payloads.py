"""Diagram extension payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from arctx.core.schema.payloads import (
    PayloadBase,
    register_payload_class,
    register_payload_decoder,
)
from arctx.core.types import JSONValue


@dataclass(frozen=True)
class DiagramPayload(PayloadBase):
    """Diagram/model artifact attached to a Node or Step.

    DiagramPayload describes the target artifact, not the ARCTX RunGraph
    topology. Its embedded node/edge data may be cyclic.
    """

    payload_id: str
    target_id: str
    target_kind: Literal["node", "step"]
    title: str | None = None
    format: str = "mermaid"
    source: str | None = None
    nodes: tuple[dict[str, JSONValue], ...] = ()
    edges: tuple[dict[str, JSONValue], ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    payload_type: str = field(default="diagram", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "title": self.title,
            "format": self.format,
            "source": self.source,
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
            "metadata": dict(self.metadata),
        }


def _diagram_from_dict(data: dict[str, JSONValue]) -> DiagramPayload:
    raw_nodes = data.get("nodes") or []
    raw_edges = data.get("edges") or []
    title = data.get("title")
    source = data.get("source")
    return DiagramPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        target_kind=data.get("target_kind", "node"),  # type: ignore[arg-type]
        title=str(title) if title is not None else None,
        format=str(data.get("format", "mermaid")),
        source=str(source) if source is not None else None,
        nodes=tuple(dict(n) for n in raw_nodes),
        edges=tuple(dict(e) for e in raw_edges),
        metadata=dict(data.get("metadata") or {}),
    )


register_payload_class(DiagramPayload)
register_payload_decoder("diagram", _diagram_from_dict)


__all__ = ["DiagramPayload"]
