"""Trace context for observed history traversal."""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class TraceContext:
    """Materialized view of observed history walking backwards from a node."""

    current_node_id: str
    past_node_ids: tuple[str, ...] = ()
    output_transition_ids: tuple[str, ...] = ()
    input_transition_ids: tuple[str, ...] = ()
    result_payload_ids: tuple[str, ...] = ()
    prediction_output_transition_ids: tuple[str, ...] = ()
    note_payload_ids: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
