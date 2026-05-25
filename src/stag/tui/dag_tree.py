"""Populate a Textual Tree widget from a RunHandle's DAG."""

from __future__ import annotations

from stag.core.cuts import inactive_node_ids, inactive_transition_ids
from stag.core.run.handle import RunHandle
from stag.core.schema.payloads import NodePayload, TransitionPayload


def _build_labels(handle: RunHandle) -> tuple[dict[str, str], dict[str, str]]:
    """Return (state_labels, plan_labels) maps from raw ID to display label.

    Nodes: S0 (root), S1, S2, ... in graph.nodes insertion order.
    Transitions: P1, P2, ... in graph.transitions insertion order.
    """
    graph = handle.run_graph
    root_id = handle.root_node_id

    state_labels: dict[str, str] = {}
    counter = 0
    state_labels[root_id] = "S0"
    for node_id in graph.nodes:
        if node_id == root_id:
            continue
        counter += 1
        state_labels[node_id] = f"S{counter}"

    plan_labels: dict[str, str] = {}
    for idx, tid in enumerate(graph.transitions, start=1):
        plan_labels[tid] = f"P{idx}"

    return state_labels, plan_labels


def _transition_type(handle: RunHandle, transition_id: str) -> str | None:
    """Return the type string of the first TransitionPayload on this transition."""
    for p in handle.run_graph.payloads_for_transition(transition_id):
        if isinstance(p, TransitionPayload):
            s = p.type
            return s if len(s) <= 60 else s[:59] + "…"
    return None


def _merged_node_label(
    handle: RunHandle,
    transition_id: str,
    output_node_id: str,
    state_labels: dict[str, str],
    plan_labels: dict[str, str],
    inactive_nodes: set[str],
    inactive_trans: set[str],
) -> str:
    """Build a merged label: [extra_inputs] [Pk type] → Sk [✂].

    This is the new style where the transition info is woven into the
    output-node row, eliminating the standalone transition TreeNode.
    """
    graph = handle.run_graph
    inputs = graph.transition_inputs(transition_id)
    pl = plan_labels.get(transition_id, transition_id)
    t_type = _transition_type(handle, transition_id) or ""
    sl = state_labels.get(output_node_id, output_node_id)

    is_node_cut = output_node_id in inactive_nodes
    is_trans_cut = transition_id in inactive_trans
    is_cut = is_node_cut or is_trans_cut

    # Extra inputs (all except primary, which is inputs[0]).
    extra_part = ""
    if len(inputs) > 1:
        others = " ".join(f"+{state_labels.get(n, n)}" for n in inputs[1:])
        extra_part = f"[{others}] "

    # Transition badge.
    type_part = f" [yellow]{t_type}[/yellow]" if t_type else ""
    plan_part = f"[bold]{pl}[/bold]{type_part}"

    # Output node label.
    if is_cut:
        node_part = f"[red strike]{sl} ✂[/red strike]"
    else:
        node_part = sl

    return f"{extra_part}[{plan_part}] → {node_part}"


def populate_dag_tree(tree, handle: RunHandle) -> tuple[dict[str, str], dict[str, str]]:
    """Populate *tree* (a Textual Tree) with the run DAG.

    Returns (state_labels, plan_labels) so callers can map display labels back
    to raw IDs without re-computing.

    Each tree node's .data is a dict with keys:
      type: "node" | "backref" | "forward_pointer" | "note" | "section"
      id:   raw graph ID (node_id or transition_id)

    Note: transitions are no longer standalone TreeNodes. Each non-root node
    row merges its incoming transition label into the node label. The node
    data always points to the output Node.  Transition payload detail is
    available in the detail pane under an "## Incoming" section.
    """
    graph = handle.run_graph
    state_labels, plan_labels = _build_labels(handle)
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_transition_ids(graph)

    visited_nodes: set[str] = set()

    def root_label(node_id: str) -> str:
        sl = state_labels.get(node_id, node_id)
        return f"[bold]{sl} (root)[/bold]"

    def add_node(parent_tree_node, node_id: str, incoming_transition_id: str | None) -> None:
        if node_id in visited_nodes:
            sl = state_labels.get(node_id, node_id)
            parent_tree_node.add_leaf(
                f"↻{sl}",
                data={"type": "backref", "id": node_id},
            )
            return

        visited_nodes.add(node_id)

        if incoming_transition_id is None:
            # Root node.
            label = root_label(node_id)
        else:
            label = _merged_node_label(
                handle,
                incoming_transition_id,
                node_id,
                state_labels,
                plan_labels,
                inactive_nodes,
                inactive_trans,
            )

        tree_node = parent_tree_node.add(label, data={"type": "node", "id": node_id})

        # Attach note-type NodePayload leaves.
        for payload in graph.payloads_for_node(node_id):
            if isinstance(payload, NodePayload) and payload.type == "note":
                text = str(payload.content.get("text", ""))
                if len(text) > 80:
                    text = text[:79] + "…"
                tree_node.add_leaf(
                    f"[dim]{text}[/dim]",
                    data={"type": "note", "id": node_id},
                )

        # Recurse through outgoing transitions.
        out_trans = graph.transitions_from_node(node_id)
        for tid in out_trans:
            inputs = graph.transition_inputs(tid)
            if inputs and inputs[0] != node_id:
                # This node is a secondary input; add a forward-pointer leaf.
                pl = plan_labels.get(tid, tid)
                primary = state_labels.get(inputs[0], inputs[0])
                tree_node.add_leaf(
                    f"▸ feeds [bold]{pl}[/bold] (@{primary})",
                    data={"type": "forward_pointer", "id": tid},
                )
                continue
            # Primary input: add the output node merged with transition info.
            out_id = graph.transition_output(tid)
            if out_id:
                add_node(tree_node, out_id, incoming_transition_id=tid)

    root_id = handle.root_node_id
    tree.clear()
    add_node(tree.root, root_id, incoming_transition_id=None)

    return state_labels, plan_labels
