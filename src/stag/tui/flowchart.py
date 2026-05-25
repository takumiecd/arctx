"""ASCII flowchart renderer for the STAG DAG.

Produces a list of Rich-markup strings (one per row) showing nodes and
transitions in layered columns.  Layout rules:
  - Center node is layer 0.
  - Forward (outgoing) transitions and output nodes get positive layer indices.
  - Backward (incoming) transitions and input nodes get negative layer indices.
  - BFS up to *depth* hops; both nodes and transitions count as one hop each.
  - Nodes: box  ┌─────┐  │ Sk  │  └─────┘
  - Transitions: diamond-ish  ◇ Pk  (single line)
  - Edges: vertical lines connecting layers.

CELL_W = 12 chars per column; 5 rows per band.
"""

from __future__ import annotations

from collections import deque

from stag.core.cuts import inactive_node_ids, inactive_transition_ids
from stag.core.run.handle import RunHandle


CELL_W = 12
BAND_H = 5  # rows per horizontal band


def _build_labels(handle: RunHandle) -> tuple[dict[str, str], dict[str, str]]:
    graph = handle.run_graph
    root_id = handle.root_node_id
    state_labels: dict[str, str] = {root_id: "S0"}
    counter = 0
    for nid in graph.nodes:
        if nid == root_id:
            continue
        counter += 1
        state_labels[nid] = f"S{counter}"
    plan_labels: dict[str, str] = {}
    for idx, tid in enumerate(graph.transitions, start=1):
        plan_labels[tid] = f"P{idx}"
    return state_labels, plan_labels


def render_flowchart(handle: RunHandle, center_node_id: str, depth: int = 2) -> list[str]:
    """Return list of Rich-markup strings representing a flowchart subgraph.

    The center node gets [reverse] highlight. Depth counts node+transition hops.
    Returns at least one line even for a single-node graph.
    """
    graph = handle.run_graph
    if center_node_id not in graph.nodes:
        # Fallback: use root.
        center_node_id = handle.root_node_id

    state_labels, plan_labels = _build_labels(handle)
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_transition_ids(graph)

    # BFS to assign layer indices.
    # We store (kind, id) -> layer.
    layers: dict[tuple[str, str], int] = {}
    queue: deque[tuple[str, str, int]] = deque()
    queue.append(("node", center_node_id, 0))

    while queue:
        kind, rid, layer = queue.popleft()
        key = (kind, rid)
        if key in layers:
            continue
        if abs(layer) > depth:
            continue
        layers[key] = layer

        if kind == "node":
            # Forward: outgoing transitions at layer+1.
            for tid in graph.transitions_from_node(rid):
                queue.append(("transition", tid, layer + 1))
            # Backward: incoming transitions at layer-1.
            for tid in graph.transitions_to_node(rid):
                queue.append(("transition", tid, layer - 1))
        else:  # transition
            # Forward: output nodes at layer+1.
            for nid in graph.transition_outputs(rid):
                queue.append(("node", nid, layer + 1))
            # Backward: input nodes at layer-1.
            for nid in graph.transition_inputs(rid):
                queue.append(("node", nid, layer - 1))

    if not layers:
        # Nothing found; render single box.
        sl = state_labels.get(center_node_id, "S?")
        return _single_node_box(sl, center=True)

    min_layer = min(layers.values())
    max_layer = max(layers.values())

    by_layer: dict[int, list[tuple[str, str]]] = {}
    for (kind, rid), layer in layers.items():
        by_layer.setdefault(layer, []).append((kind, rid))

    max_items = max(len(v) for v in by_layer.values())
    total_cols = max(max_items * CELL_W, CELL_W)

    markup_lines = _build_markup_lines(
        handle,
        by_layer,
        state_labels,
        plan_labels,
        inactive_nodes,
        inactive_trans,
        center_node_id,
        min_layer,
        max_layer,
        total_cols,
    )

    # Strip trailing empty lines.
    while markup_lines and not markup_lines[-1].strip():
        markup_lines.pop()

    return markup_lines if markup_lines else [f"[bold]{state_labels.get(center_node_id, 'S?')}[/bold]"]


def _single_node_box(label: str, *, center: bool) -> list[str]:
    half = max(len(label) // 2 + 1, 3)
    width = half * 2 + 2
    top = "┌" + "─" * (width - 2) + "┐"
    mid_pad = (width - 2 - len(label)) // 2
    mid = "│" + " " * mid_pad + label + " " * (width - 2 - mid_pad - len(label)) + "│"
    bot = "└" + "─" * (width - 2) + "┘"
    if center:
        return [f"[reverse]{top}[/reverse]", f"[reverse]{mid}[/reverse]", f"[reverse]{bot}[/reverse]"]
    return [top, mid, bot]


def _build_markup_lines(
    handle,
    by_layer,
    state_labels,
    plan_labels,
    inactive_nodes,
    inactive_trans,
    center_node_id,
    min_layer,
    max_layer,
    total_cols,
) -> list[str]:
    """Build Rich markup lines directly (simpler than post-processing the char buf)."""
    graph = handle.run_graph
    output: list[str] = []

    for layer_idx in range(min_layer, max_layer + 1):
        items = by_layer.get(layer_idx, [])
        band_rows: list[list[str]] = [[""] * total_cols for _ in range(BAND_H)]
        n_items = len(items)
        spacing = total_cols // (n_items + 1) if n_items else total_cols // 2

        for pos, (kind, rid) in enumerate(items):
            col_center = spacing * (pos + 1)

            if kind == "node":
                sl = state_labels.get(rid, "?")
                is_cut = rid in inactive_nodes
                is_center = rid == center_node_id
                color = "red" if is_cut else "white"
                wrap_open = "[reverse]" if is_center else f"[{color}]"
                wrap_close = "[/reverse]" if is_center else f"[/{color}]"
                label = f"✂{sl}" if is_cut else sl
                label = label[:6]
                half = max(len(label) // 2 + 1, 3)
                left = col_center - half
                right = col_center + half
                box_w = right - left + 1
                top_str = "┌" + "─" * (box_w - 2) + "┐"
                pad = box_w - 2 - len(label)
                lpad = pad // 2
                mid_str = "│" + " " * lpad + label + " " * (pad - lpad) + "│"
                bot_str = "└" + "─" * (box_w - 2) + "┘"

                def place(row_idx, c, s):
                    if 0 <= c < total_cols:
                        band_rows[row_idx][c] = s

                place(1, left, f"{wrap_open}{top_str}{wrap_close}")
                place(2, left, f"{wrap_open}{mid_str}{wrap_close}")
                place(3, left, f"{wrap_open}{bot_str}{wrap_close}")

            else:  # transition
                pl = plan_labels.get(rid, "?")
                is_cut = rid in inactive_trans
                color = "red" if is_cut else "cyan"
                text = f"◇ {pl}"
                band_rows[2][col_center] = f"[{color}]{text}[/{color}]"

        # Collapse each band row to a single string.
        for row_cells in band_rows:
            parts = [c for c in row_cells if c]
            output.append(" ".join(parts) if parts else "")

    return output
