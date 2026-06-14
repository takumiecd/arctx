"""RunHandle node mutation helpers."""

from __future__ import annotations

from arctx.core.schema.graph import Node


def add_node_impl(
    self,
    *,
    metadata: dict | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> Node:
    """Create one standalone Node."""
    node = Node(node_id=self._next_id("n"), metadata=dict(metadata or {}))
    self.run_graph.add_node(node)
    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="node_added",
        target_kind="node",
        target_id=node.node_id,
        created_records=(node.node_id,),
    )
    return node
