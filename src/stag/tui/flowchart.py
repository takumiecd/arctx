"""ASCII flowchart renderer for the STAG DAG.

Produces a list of Rich-markup strings (one per row) showing nodes and
transitions in layered columns.  Layout rules:
  - Center node is layer 0.
  - Forward (outgoing) transitions and output nodes get positive layer indices.
  - Backward (incoming) transitions and input nodes get negative layer indices.
  - BFS up to *depth* hops; both nodes and transitions count as one hop each.
  - Nodes: box  ┌─────┐  │ Sk  │  └─────┘
  - Transitions: diamond-ish  ◇ Pk  (single line)
  - Edges: vertical/L-shape connector lines between layers.

CELL_W = 12 chars per column; BAND_H = 5 rows per band.
A GAP_H = 2 rows between bands is used for connectors.
"""

from __future__ import annotations

import re
from collections import deque

from stag.core.cuts import inactive_node_ids, inactive_transition_ids
from stag.core.run.handle import RunHandle


CELL_W = 12
BAND_H = 5   # rows per content band
GAP_H = 2    # rows between bands (used for connectors)


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

    # Assign column centers for each item in each layer.
    # col_centers[(kind, rid)] = character column index of the item's center.
    max_items = max(len(v) for v in by_layer.values())
    total_cols = max(max_items * CELL_W, CELL_W)

    col_centers: dict[tuple[str, str], int] = {}
    for layer_idx in range(min_layer, max_layer + 1):
        items = by_layer.get(layer_idx, [])
        n_items = len(items)
        spacing = total_cols // (n_items + 1) if n_items else total_cols // 2
        for pos, item in enumerate(items):
            col_centers[item] = spacing * (pos + 1)

    markup_lines = _build_markup_lines(
        handle,
        by_layer,
        col_centers,
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


def _char_buf_to_line(buf_row: list[str]) -> str:
    """Collapse a character buffer row (list of single chars or '') to a string."""
    return "".join(buf_row)


def _build_markup_lines(
    handle,
    by_layer,
    col_centers,
    state_labels,
    plan_labels,
    inactive_nodes,
    inactive_trans,
    center_node_id,
    min_layer,
    max_layer,
    total_cols,
) -> list[str]:
    """Build Rich markup lines with connector lines between layers."""
    graph = handle.run_graph
    output: list[str] = []

    n_layers = max_layer - min_layer + 1
    # Total rows: each layer occupies BAND_H rows; gaps between layers get GAP_H rows.
    # Layer i (0-indexed from min_layer) starts at row i * (BAND_H + GAP_H).
    def layer_start_row(layer_idx: int) -> int:
        return (layer_idx - min_layer) * (BAND_H + GAP_H)

    total_rows = layer_start_row(max_layer) + BAND_H

    # Build a plain-text connector buffer (no markup, just box-drawing chars).
    # We'll overlay it under the markup content.
    conn_buf: list[list[str]] = [[" "] * total_cols for _ in range(total_rows)]

    def conn_set(r: int, c: int, ch: str) -> None:
        if 0 <= r < total_rows and 0 <= c < total_cols:
            # Don't overwrite a non-space char with a space.
            if ch != " " or conn_buf[r][c] == " ":
                conn_buf[r][c] = ch

    # Draw connectors for each adjacent layer pair.
    for layer_idx in range(min_layer, max_layer):
        upper_items = by_layer.get(layer_idx, [])
        lower_items = by_layer.get(layer_idx + 1, [])

        upper_row_end = layer_start_row(layer_idx) + BAND_H - 1   # bottom of upper band
        lower_row_start = layer_start_row(layer_idx + 1)            # top of lower band
        # Gap rows are [upper_row_end+1 .. lower_row_start-1]

        for u_item in upper_items:
            u_kind, u_rid = u_item
            u_col = col_centers.get(u_item, 0)

            # Find all lower items connected to this upper item.
            connected_lower: list[tuple[str, str]] = []

            for l_item in lower_items:
                l_kind, l_rid = l_item
                connected = False

                if u_kind == "node" and l_kind == "transition":
                    # Edge if u_rid is an input of l_rid.
                    connected = u_rid in graph.transition_inputs(l_rid)
                elif u_kind == "transition" and l_kind == "node":
                    # Edge if l_rid is the output of u_rid.
                    connected = graph.transition_output(u_rid) == l_rid

                if connected:
                    connected_lower.append(l_item)

            for l_item in connected_lower:
                l_col = col_centers.get(l_item, 0)

                # Draw a vertical segment from bottom of upper band down through
                # the gap to the top of the lower band.  For non-vertical paths
                # (where columns differ), draw an L-shape.

                # Vertical segment downward from upper item's bottom.
                for r in range(upper_row_end, lower_row_start + 1):
                    conn_set(r, u_col, "│")

                if u_col != l_col:
                    # Horizontal segment in the middle of the gap.
                    gap_mid = (upper_row_end + lower_row_start) // 2
                    # Draw horizontal from u_col to l_col at gap_mid.
                    lo_col = min(u_col, l_col)
                    hi_col = max(u_col, l_col)
                    for c in range(lo_col, hi_col + 1):
                        conn_set(gap_mid, c, "─")
                    # Corner at the turn.
                    if u_col < l_col:
                        conn_set(gap_mid, u_col, "└")
                    else:
                        conn_set(gap_mid, u_col, "┘")
                    # Vertical from gap_mid down to lower_row_start.
                    for r in range(gap_mid, lower_row_start + 1):
                        conn_set(r, l_col, "│")
                    # Erase any stray │ above gap_mid at u_col that are now
                    # replaced by the L-corner (keep them for multi-fan cases).

    # Now build the actual markup-augmented output by merging:
    # - conn_buf rows (plain text, dim-colored)
    # - band_rows (markup strings placed at specific columns within each band)
    #
    # Strategy: produce one output line per total_rows row.
    # For content rows (within a band), overlay markup items on top of connector.
    # For gap rows, emit connector only.

    # First, accumulate per-row markup placements from the content bands.
    # row_markup[r] = list of (col, markup_string) for items placed in that row.
    row_markup: dict[int, list[tuple[int, str]]] = {}

    for layer_idx in range(min_layer, max_layer + 1):
        items = by_layer.get(layer_idx, [])
        band_start = layer_start_row(layer_idx)

        for item in items:
            kind, rid = item
            col_center = col_centers.get(item, 0)

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
                box_w = half * 2 + 1
                top_str = "┌" + "─" * (box_w - 2) + "┐"
                pad = box_w - 2 - len(label)
                lpad = pad // 2
                mid_str = "│" + " " * lpad + label + " " * (pad - lpad) + "│"
                bot_str = "└" + "─" * (box_w - 2) + "┘"

                row_markup.setdefault(band_start + 1, []).append(
                    (left, f"{wrap_open}{top_str}{wrap_close}")
                )
                row_markup.setdefault(band_start + 2, []).append(
                    (left, f"{wrap_open}{mid_str}{wrap_close}")
                )
                row_markup.setdefault(band_start + 3, []).append(
                    (left, f"{wrap_open}{bot_str}{wrap_close}")
                )

            else:  # transition
                pl = plan_labels.get(rid, "?")
                is_cut = rid in inactive_trans
                color = "red" if is_cut else "cyan"
                text = f"◇ {pl}"
                row_markup.setdefault(band_start + 2, []).append(
                    (col_center, f"[{color}]{text}[/{color}]")
                )

    # Render each row: connector background + markup overlay.
    for r in range(total_rows):
        conn_row = "".join(conn_buf[r])
        placements = row_markup.get(r, [])

        if not placements:
            # Pure connector row.
            stripped = conn_row.rstrip()
            if stripped:
                output.append(f"[$accent 50%]{stripped}[/$accent 50%]")
            else:
                output.append("")
        else:
            # Build output line by overlaying markup strings at their column
            # positions onto the connector background.  We produce a list of
            # segments, rendering connector chars as dim and markup items as-is.
            # Sort placements by column.
            placements_sorted = sorted(placements, key=lambda x: x[0])
            segments: list[str] = []
            cursor = 0
            for col, markup_str in placements_sorted:
                if col > cursor:
                    bg_slice = conn_row[cursor:col].rstrip(" ")
                    if bg_slice:
                        segments.append(f"[$accent 50%]{bg_slice}[/$accent 50%]")
                    # Fill gap with spaces.
                    gap_spaces = col - cursor - len(bg_slice)
                    if gap_spaces > 0:
                        segments.append(" " * gap_spaces)
                elif col < cursor:
                    # Overlap: skip (markup takes priority).
                    pass
                segments.append(markup_str)
                # Advance cursor past a rough estimate of the markup string's
                # visible width (strip Rich markup tags to count chars).
                visible = re.sub(r"\[[^\]]*\]", "", markup_str)
                cursor = col + len(visible)
            output.append("".join(segments))

    return output
