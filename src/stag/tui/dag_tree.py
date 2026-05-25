"""Populate a Textual Tree widget from a RunHandle's DAG."""

from __future__ import annotations

from stag.core.cuts import inactive_node_ids, inactive_transition_ids
from stag.core.run.handle import RunHandle
from stag.core.schema.payloads import NotePayload, PlanPayload


def _build_labels(handle: RunHandle) -> tuple[dict[str, str], dict[str, str]]:
    """Return (state_labels, plan_labels) maps from raw ID to display label.

    Nodes: S0 (root), S1, S2, ... in graph.nodes insertion order.
    Transitions: P1, P2, ... in graph.transitions insertion order.
    """
    graph = handle.run_graph
    root_id = handle.root_node_id

    state_labels: dict[str, str] = {}
    counter = 0
    # Root always S0.
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


def _plan_intent(handle: RunHandle, transition_id: str) -> str | None:
    for p in handle.run_graph.payloads_for_transition(transition_id):
        if isinstance(p, PlanPayload):
            s = p.intent
            return s if len(s) <= 60 else s[:59] + "…"
    return None


def populate_dag_tree(tree, handle: RunHandle) -> tuple[dict[str, str], dict[str, str]]:
    """Populate *tree* (a Textual Tree) with the run DAG.

    Returns (state_labels, plan_labels) so callers can map display labels back
    to raw IDs without re-computing.

    Each tree node's .data is a dict with keys:
      type: "node" | "transition" | "backref" | "forward_pointer" | "note" | "section"
      id:   raw graph ID (node_id or transition_id)
    """
    graph = handle.run_graph
    state_labels, plan_labels = _build_labels(handle)
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_transition_ids(graph)

    visited_nodes: set[str] = set()
    visited_trans: set[str] = set()

    def node_label(node_id: str) -> str:
        sl = state_labels.get(node_id, node_id)
        is_root = node_id == handle.root_node_id
        is_cut = node_id in inactive_nodes

        if is_cut:
            return f"[red strike]{sl} ✂[/red strike]"
        if is_root:
            return f"[bold]{sl} (root)[/bold]"

        # Determine role from incoming transitions.
        incoming = graph.transitions_to_node(node_id)
        if incoming:
            kind = graph.transition_kind(incoming[0])
            if kind == "result":
                return sl  # default colour
            if kind == "prediction":
                return f"[cyan]{sl}[/cyan]"
        return sl

    def transition_label(transition_id: str) -> str:
        pl = plan_labels.get(transition_id, transition_id)
        is_cut = transition_id in inactive_trans
        intent = _plan_intent(handle, transition_id) or ""
        inputs = graph.transition_inputs(transition_id)

        # Extra input labels beyond the primary.
        extra = ""
        if len(inputs) > 1:
            others = " ".join(f"(+{state_labels.get(n, n)})" for n in inputs[1:])
            extra = f" {others}"

        cut_marker = " ✂" if is_cut else ""
        intent_part = f" [yellow]{intent}[/yellow]" if intent else ""
        return f"[bold]{pl}[/bold]{intent_part}{extra}{cut_marker}"

    def add_node(parent_tree_node, node_id: str, *, is_last: bool) -> None:
        if node_id in visited_nodes:
            sl = state_labels.get(node_id, node_id)
            parent_tree_node.add_leaf(
                f"↻{sl}",
                data={"type": "backref", "id": node_id},
            )
            return

        visited_nodes.add(node_id)
        label = node_label(node_id)
        tree_node = parent_tree_node.add(label, data={"type": "node", "id": node_id})

        # Attach note as child leaf.
        for payload in graph.payloads_for_node(node_id):
            if isinstance(payload, NotePayload):
                text = payload.text
                if len(text) > 80:
                    text = text[:79] + "…"
                tree_node.add_leaf(
                    f"[dim]{text}[/dim]",
                    data={"type": "note", "id": node_id},
                )

        # Recurse into outgoing transitions.
        out_trans = graph.transitions_from_node(node_id)
        for tid in out_trans:
            inputs = graph.transition_inputs(tid)
            # If this node is not the primary (first) input, add a forward pointer.
            if inputs and inputs[0] != node_id:
                pl = plan_labels.get(tid, tid)
                primary = state_labels.get(inputs[0], inputs[0])
                tree_node.add_leaf(
                    f"▸ feeds [bold]{pl}[/bold] (@{primary})",
                    data={"type": "forward_pointer", "id": tid},
                )
                continue
            add_transition(tree_node, tid)

    def add_transition(parent_tree_node, transition_id: str) -> None:
        if transition_id in visited_trans:
            pl = plan_labels.get(transition_id, transition_id)
            parent_tree_node.add_leaf(
                f"↻{pl}",
                data={"type": "backref", "id": transition_id},
            )
            return

        visited_trans.add(transition_id)
        label = transition_label(transition_id)
        t_node = parent_tree_node.add(label, data={"type": "transition", "id": transition_id})

        kind = graph.transition_kind(transition_id)
        marker = "→" if kind == "result" else "⇢" if kind == "prediction" else "◇"
        color = "green" if kind == "result" else "cyan" if kind == "prediction" else "white"

        outputs = graph.transition_outputs(transition_id)
        for out_id in outputs:
            sl = state_labels.get(out_id, out_id)
            child_label = f"[{color}]{marker} {sl}[/{color}]"
            child = t_node.add(child_label, data={"type": "node", "id": out_id})
            # Recurse through child subtree reusing add_node logic inlined to avoid
            # double-adding the tree node we just created.
            _recurse_from_node(child, out_id)

    def _recurse_from_node(tree_node, node_id: str) -> None:
        """Add note leaves and outgoing transitions under an already-created tree node."""
        if node_id in visited_nodes:
            return
        visited_nodes.add(node_id)

        for payload in graph.payloads_for_node(node_id):
            if isinstance(payload, NotePayload):
                text = payload.text
                if len(text) > 80:
                    text = text[:79] + "…"
                tree_node.add_leaf(
                    f"[dim]{text}[/dim]",
                    data={"type": "note", "id": node_id},
                )

        out_trans = graph.transitions_from_node(node_id)
        for tid in out_trans:
            inputs = graph.transition_inputs(tid)
            if inputs and inputs[0] != node_id:
                pl = plan_labels.get(tid, tid)
                primary = state_labels.get(inputs[0], inputs[0])
                tree_node.add_leaf(
                    f"▸ feeds [bold]{pl}[/bold] (@{primary})",
                    data={"type": "forward_pointer", "id": tid},
                )
                continue
            add_transition(tree_node, tid)

    root_id = handle.root_node_id
    tree.clear()
    add_node(tree.root, root_id, is_last=True)

    return state_labels, plan_labels
