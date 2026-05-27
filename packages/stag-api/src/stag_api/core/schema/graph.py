"""Pure DAG records.

Node and Transition form the DAG skeleton. Transition carries its own
connectivity (input_node_ids, output_node_id). Domain meaning is attached
separately as payload records.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stag_api.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class Node:
    """A pure DAG node."""

    node_id: str
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class Transition:
    """A pure DAG transition with explicit connectivity.

    Many input nodes -> one output node. The output node is always created
    before or alongside the Transition.
    """

    transition_id: str
    input_node_ids: tuple[str, ...] = ()
    output_node_id: str = ""
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
