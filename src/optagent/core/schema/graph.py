"""Pure graph elements: Node, InputTransition, OutputTransition.

Domain data is stored in attached payloads, not on these records.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class Node:
    """A pure graph node."""

    node_id: str
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class InputTransition:
    """Entry point of an operation from one or more input nodes.

    Carries no domain data itself; domain intent is attached via PlanPayload.
    """

    input_transition_id: str
    input_node_ids: tuple[str, ...]
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class OutputTransition:
    """Result edge from an InputTransition to a single output node.

    The type of result (prediction vs observed) is determined by the
    payload attached to this record (PredictionPayload vs ResultPayload).
    """

    output_transition_id: str
    input_transition_id: str
    to_node_id: str
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
