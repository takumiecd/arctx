"""ASCII flowchart renderer for the STAG DAG.

Produces a list of Rich-markup strings (one per row) showing nodes and
transitions in layered columns.  Layout rules:
  - Center node is layer 0.
  - Forward (outgoing) transitions and output nodes get positive layer indices.
  - Backward (incoming) transitions and input nodes get negative layer indices.
  - BFS up to *depth* hops; both nodes and transitions count as one hop each.
  - Nodes: box  ┌─────┐  │ Sk  │  └─────┘
  - Transitions: diamond-ish  ◇ Pk type  (single line)
  - Edges: vertical/L-shape connector lines between layers.

CELL_W = 14 chars per column; BAND_H = 5 rows per band.
A GAP_H = 2 rows between bands is used for connectors.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from typing import Literal

from stag.core.cuts import inactive_node_ids, inactive_transition_ids
from stag.core.run.handle import RunHandle


CELL_W = 14
BAND_H = 5   # rows per content band
GAP_H = 2    # rows between bands (used for connectors)


@dataclass
class ClickRegion:
    row: int         # 0-indexed line within the rendered output
    col_start: int   # inclusive visible-char column
    col_end: int     # inclusive visible-char column
    kind: Literal["node", "transition"]
    raw_id: str


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


def _transition_type(handle: RunHandle, transition_id: str) -> str:
    """Return the type string of the first TransitionPayload on this transition."""
    from stag.core.schema.payloads import TransitionPayload
    for p in handle.run_graph.payloads_for_transition(transition_id):
        if isinstance(p, TransitionPayload):
            s = p.type
            return s if len(s) <= 20 else s[:19] + "…"
    return ""


def render_flowchart(
    handle: RunHandle,
    center_node_id: str,
    depth: int = 2,
) -> tuple[list[str], list[ClickRegion]]:
    """Return (lines, click_regions) representing a flowchart subgraph.

    lines: list of Rich-markup strings (one per rendered row).
    click_regions: list of ClickRegion describing clickable areas in visible-char coords.

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
            for tid in graph.transitions_from_node(rid):
                queue.append(("transition", tid, layer + 1))
            for tid in graph.transitions_to_node(rid):
                queue.append(("transition", tid, layer - 1))
        else:  # transition
            for nid in graph.transition_outputs(rid):
                queue.append(("node", nid, layer + 1))
            for nid in graph.transition_inputs(rid):
                queue.append(("node", nid, layer - 1))

    if not layers:
        sl = state_labels.get(center_node_id, "S?")
        lines = _single_node_box(sl, center=True)
        # Emit click regions for the single-node box.
        box_w = max(len(sl) // 2 + 1, 3) * 2 + 3
        regions = [
            ClickRegion(row=i, col_start=0, col_end=box_w - 1, kind="node", raw_id=center_node_id)
            for i in range(len(lines))
        ]
        return lines, regions

    min_layer = min(layers.values())
    max_layer = max(layers.values())

    by_layer: dict[int, list[tuple[str, str]]] = {}
    for (kind, rid), layer in layers.items():
        by_layer.setdefault(layer, []).append((kind, rid))

    max_items = max(len(v) for v in by_layer.values())
    total_cols = max(max_items * CELL_W, CELL_W)

    col_centers: dict[tuple[str, str], int] = {}
    for layer_idx in range(min_layer, max_layer + 1):
        items = by_layer.get(layer_idx, [])
        n_items = len(items)
        spacing = total_cols // (n_items + 1) if n_items else total_cols // 2
        for pos, item in enumerate(items):
            col_centers[item] = spacing * (pos + 1)

    markup_lines, regions = _build_markup_lines(
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

    if not markup_lines:
        sl = state_labels.get(center_node_id, "S?")
        return [f"[bold]{sl}[/bold]"], []

    return markup_lines, regions


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
) -> tuple[list[str], list[ClickRegion]]:
    """Build Rich markup lines with connector lines between layers.

    Also returns click regions (visible-char coords) for all nodes and transitions.
    """
    graph = handle.run_graph
    output: list[str] = []
    regions: list[ClickRegion] = []

    def layer_start_row(layer_idx: int) -> int:
        return (layer_idx - min_layer) * (BAND_H + GAP_H)

    total_rows = layer_start_row(max_layer) + BAND_H

    # Build a plain-text connector buffer.
    conn_buf: list[list[str]] = [[" "] * total_cols for _ in range(total_rows)]

    def conn_set(r: int, c: int, ch: str) -> None:
        if 0 <= r < total_rows and 0 <= c < total_cols:
            if ch != " " or conn_buf[r][c] == " ":
                conn_buf[r][c] = ch

    # Draw connectors for each adjacent layer pair.
    for layer_idx in range(min_layer, max_layer):
        upper_items = by_layer.get(layer_idx, [])
        lower_items = by_layer.get(layer_idx + 1, [])

        upper_row_end = layer_start_row(layer_idx) + BAND_H - 1
        lower_row_start = layer_start_row(layer_idx + 1)

        for u_item in upper_items:
            u_kind, u_rid = u_item
            u_col = col_centers.get(u_item, 0)

            connected_lower: list[tuple[str, str]] = []

            for l_item in lower_items:
                l_kind, l_rid = l_item
                connected = False

                if u_kind == "node" and l_kind == "transition":
                    connected = u_rid in graph.transition_inputs(l_rid)
                elif u_kind == "transition" and l_kind == "node":
                    connected = graph.transition_output(u_rid) == l_rid

                if connected:
                    connected_lower.append(l_item)

            for l_item in connected_lower:
                l_col = col_centers.get(l_item, 0)

                for r in range(upper_row_end, lower_row_start + 1):
                    conn_set(r, u_col, "│")

                if u_col != l_col:
                    gap_mid = (upper_row_end + lower_row_start) // 2
                    lo_col = min(u_col, l_col)
                    hi_col = max(u_col, l_col)
                    for c in range(lo_col, hi_col + 1):
                        conn_set(gap_mid, c, "─")
                    if u_col < l_col:
                        conn_set(gap_mid, u_col, "└")
                    else:
                        conn_set(gap_mid, u_col, "┘")
                    for r in range(gap_mid, lower_row_start + 1):
                        conn_set(r, l_col, "│")

    # Accumulate per-row markup placements and click regions from content bands.
    # row_markup[r] = list of (col, markup_string, visible_len, kind, raw_id)
    # where kind/raw_id may be None for non-clickable overlays.
    row_markup: dict[int, list[tuple[int, str, int, str | None, str | None]]] = {}

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

                # Add 1-char padding around box for easier clicking.
                click_left = max(0, left - 1)
                click_right = left + box_w  # inclusive

                for sub_row, box_str in [(1, top_str), (2, mid_str), (3, bot_str)]:
                    abs_row = band_start + sub_row
                    row_markup.setdefault(abs_row, []).append(
                        (left, f"{wrap_open}{box_str}{wrap_close}", box_w, "node", rid)
                    )
                    regions.append(ClickRegion(
                        row=abs_row,
                        col_start=click_left,
                        col_end=click_right,
                        kind="node",
                        raw_id=rid,
                    ))

            else:  # transition
                pl = plan_labels.get(rid, "?")
                t_type = _transition_type(handle, rid)
                is_cut = rid in inactive_trans
                color = "red" if is_cut else "cyan"
                # Show: ◇ P1 experiment (truncated to fit cell width)
                label_full = f"◇ {pl}"
                if t_type:
                    label_full = f"◇ {pl} {t_type}"
                # Truncate to CELL_W - 1
                if len(label_full) > CELL_W - 1:
                    label_full = label_full[:CELL_W - 2] + "…"
                text = label_full
                visible_len = len(text)
                abs_row = band_start + 2
                row_markup.setdefault(abs_row, []).append(
                    (col_center, f"[{color}]{text}[/{color}]", visible_len, "transition", rid)
                )
                regions.append(ClickRegion(
                    row=abs_row,
                    col_start=max(0, col_center - 1),
                    col_end=col_center + visible_len,
                    kind="transition",
                    raw_id=rid,
                ))

    # Render each row: connector background + markup overlay.
    for r in range(total_rows):
        conn_row = "".join(conn_buf[r])
        placements = row_markup.get(r, [])

        if not placements:
            stripped = conn_row.rstrip()
            if stripped:
                output.append(f"[$accent 50%]{stripped}[/$accent 50%]")
            else:
                output.append("")
        else:
            placements_sorted = sorted(placements, key=lambda x: x[0])
            segments: list[str] = []
            cursor = 0
            for col, markup_str, visible_len, _kind, _rid in placements_sorted:
                if col > cursor:
                    bg_slice = conn_row[cursor:col].rstrip(" ")
                    if bg_slice:
                        segments.append(f"[$accent 50%]{bg_slice}[/$accent 50%]")
                    gap_spaces = col - cursor - len(bg_slice)
                    if gap_spaces > 0:
                        segments.append(" " * gap_spaces)
                elif col < cursor:
                    pass
                segments.append(markup_str)
                cursor = col + visible_len
            output.append("".join(segments))

    return output, regions
