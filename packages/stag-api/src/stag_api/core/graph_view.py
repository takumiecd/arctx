"""GraphView: a named label anchored to a root node in RunGraph.

The contents of a view are determined at read time by reachability from
root_node_id via output transitions. No membership sets are stored.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stag_api.core.types import JSONValue, to_jsonable


@dataclass
class GraphView:
    """A named label for a subgraph rooted at a single node."""

    view_id: str
    name: str
    root_node_id: str
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        d = to_jsonable(self)
        assert isinstance(d, dict)
        return d  # type: ignore[return-value]
