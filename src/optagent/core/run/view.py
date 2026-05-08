"""RunHandle.view_* implementations."""

from __future__ import annotations

from optagent.core.graph_view import GraphView
from optagent.core.schema.payloads import ResultPayload


def view_create_impl(
    self,
    name: str,
    *,
    root_node_ids: list[str] | tuple[str, ...],
) -> GraphView:
    """Create a new GraphView with the given roots.

    The view starts with only the root nodes in its membership.
    Records are added as plan/observe/predict operations target the view.
    """
    if name in self.views:
        raise ValueError(f"view already exists: {name!r}")
    for nid in root_node_ids:
        if nid not in self.run_graph.nodes:
            raise KeyError(f"unknown node_id: {nid}")

    view_id = self._next_id("pl")  # reuse pl counter for view IDs
    view = GraphView(
        view_id=f"view_{name}",
        name=name,
        root_node_ids=tuple(root_node_ids),
        node_ids=set(root_node_ids),
    )
    self.views[name] = view
    return view


def view_list_impl(self) -> list[GraphView]:
    """Return all GraphViews."""
    return list(self.views.values())


def view_show_impl(self, name: str) -> GraphView:
    """Return a named GraphView."""
    return self._get_view(name)


def view_merge_impl(
    self,
    name: str,
    *,
    into: str = "main",
    to_node_id: str | None = None,
) -> GraphView:
    """Add the records from *name* view into the *into* view.

    If to_node_id is given, only the path from root to that node is merged.
    Otherwise all records from the source view are merged.
    """
    src = self._get_view(name)
    dst = self._get_view(into)

    if to_node_id is not None:
        # Merge only the path from root → to_node_id via observed OTs
        node_ids, it_ids, ot_ids = _path_to_node(self, to_node_id, src)
        dst.node_ids.update(node_ids)
        dst.input_transition_ids.update(it_ids)
        dst.output_transition_ids.update(ot_ids)
        dst.payload_ids.update(_payload_ids_for_records(self, node_ids, it_ids, ot_ids))
    else:
        dst.node_ids.update(src.node_ids)
        dst.input_transition_ids.update(src.input_transition_ids)
        dst.output_transition_ids.update(src.output_transition_ids)
        dst.payload_ids.update(src.payload_ids)

    return dst


def _path_to_node(
    handle, to_node_id: str, view: GraphView
) -> tuple[set[str], set[str], set[str]]:
    """Collect node/IT/OT IDs on the path from any root of view to to_node_id."""
    node_ids: set[str] = {to_node_id}
    it_ids: set[str] = set()
    ot_ids: set[str] = set()

    cursor = to_node_id
    while cursor not in view.root_node_ids:
        incoming = handle.run_graph.output_transitions_to_node.get(cursor, [])
        observed_ot = None
        for ot_id in reversed(incoming):
            if ot_id in view.output_transition_ids:
                ot_payloads = handle.run_graph.payloads_for_output_transition(ot_id)
                if any(isinstance(p, ResultPayload) for p in ot_payloads):
                    observed_ot = handle.run_graph.output_transitions[ot_id]
                    break
        if observed_ot is None:
            break
        ot_ids.add(observed_ot.output_transition_id)
        it = handle.run_graph.input_transitions[observed_ot.input_transition_id]
        it_ids.add(it.input_transition_id)
        for nid in it.input_node_ids:
            node_ids.add(nid)
        cursor = it.input_node_ids[0] if it.input_node_ids else cursor

    return node_ids, it_ids, ot_ids


def _payload_ids_for_records(
    handle,
    node_ids: set[str],
    input_transition_ids: set[str],
    output_transition_ids: set[str],
) -> set[str]:
    payload_ids: set[str] = set()
    for node_id in node_ids:
        payload_ids.update(handle.run_graph.payloads_by_node.get(node_id, ()))
    for it_id in input_transition_ids:
        payload_ids.update(handle.run_graph.payloads_by_input_transition.get(it_id, ()))
    for ot_id in output_transition_ids:
        payload_ids.update(handle.run_graph.payloads_by_output_transition.get(ot_id, ()))
    return payload_ids
