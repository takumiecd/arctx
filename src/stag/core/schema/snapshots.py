"""Trace context for history traversal."""

from __future__ import annotations

from dataclasses import dataclass, field

from stag.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class TraceContext:
    """Materialized view of history walking backwards from a node."""

    current_node_id: str
    past_node_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    payload_ids: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
