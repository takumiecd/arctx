"""GraphView: a named subset of RunGraph records.

A GraphView tracks which nodes, input transitions, output transitions, and
payloads belong to a named exploration context. Records are never copied;
the view only stores IDs. Multiple views can share the same underlying records.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.types import JSONValue, to_jsonable


@dataclass
class GraphView:
    """A named subset of RunGraph records."""

    view_id: str
    name: str
    root_node_ids: tuple[str, ...]
    node_ids: set[str] = field(default_factory=set)
    input_transition_ids: set[str] = field(default_factory=set)
    output_transition_ids: set[str] = field(default_factory=set)
    payload_ids: set[str] = field(default_factory=set)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        d = to_jsonable(self)
        assert isinstance(d, dict)
        d["node_ids"] = sorted(self.node_ids)
        d["input_transition_ids"] = sorted(self.input_transition_ids)
        d["output_transition_ids"] = sorted(self.output_transition_ids)
        d["payload_ids"] = sorted(self.payload_ids)
        return d  # type: ignore[return-value]
