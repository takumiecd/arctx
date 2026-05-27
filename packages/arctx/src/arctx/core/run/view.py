"""RunHandle.view_* implementations."""

from __future__ import annotations

from arctx.core.graph_view import GraphView


def view_create_impl(
    self,
    name: str,
    *,
    root_node_id: str,
) -> GraphView:
    """Create a new GraphView anchored at a single root node."""
    if root_node_id not in self.run_graph.nodes:
        raise KeyError(f"unknown node_id: {root_node_id}")

    view = GraphView(
        view_id=f"view_{name}",
        name=name,
        root_node_id=root_node_id,
    )
    self.run_graph.add_view(view)
    return view


def view_list_impl(self) -> list[GraphView]:
    """Return all GraphViews."""
    return list(self.run_graph.views.values())


def view_show_impl(self, name: str) -> GraphView:
    """Return a named GraphView."""
    return self._get_view(name)
