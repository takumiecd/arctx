"""Generate a standalone HTML page with inline SVG for the run graph."""

from __future__ import annotations

from stag.core.cuts import inactive_node_ids, inactive_transition_ids
from stag.core.run.handle import RunHandle


_NODE_W = 90
_NODE_H = 36
_TRANS_W = 70
_TRANS_H = 28
_H_GAP = 60   # horizontal gap between layers
_V_GAP = 50   # vertical gap between items in same layer
_MARGIN = 40


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


def _assign_layers(handle: RunHandle) -> dict[tuple[str, str], int]:
    """BFS from root to assign layers. Returns (kind, id) -> layer."""
    from collections import deque

    graph = handle.run_graph
    root_id = handle.root_node_id
    layers: dict[tuple[str, str], int] = {}
    queue: deque[tuple[str, str, int]] = deque()
    queue.append(("node", root_id, 0))

    while queue:
        kind, rid, layer = queue.popleft()
        key = (kind, rid)
        if key in layers:
            continue
        layers[key] = layer
        if kind == "node":
            for tid in graph.transitions_from_node(rid):
                queue.append(("transition", tid, layer + 1))
        else:
            for nid in graph.transition_outputs(rid):
                queue.append(("node", nid, layer + 1))

    return layers


def render_graph_html(handle: RunHandle) -> str:
    """Return a standalone HTML page with the run graph as inline SVG."""
    graph = handle.run_graph
    state_labels, plan_labels = _build_labels(handle)
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_transition_ids(graph)
    layers = _assign_layers(handle)

    # Group by layer.
    by_layer: dict[int, list[tuple[str, str]]] = {}
    for (kind, rid), layer in layers.items():
        by_layer.setdefault(layer, []).append((kind, rid))

    # Compute (x, y) positions for each item.
    positions: dict[tuple[str, str], tuple[float, float]] = {}
    max_layer = max(layers.values()) if layers else 0

    for layer_idx in range(max_layer + 1):
        items = by_layer.get(layer_idx, [])
        n = len(items)
        x = _MARGIN + layer_idx * (_NODE_W + _H_GAP)
        for pos, item in enumerate(items):
            y = _MARGIN + pos * (_NODE_H + _V_GAP)
            positions[item] = (x + _NODE_W / 2, y + _NODE_H / 2)

    svg_width = _MARGIN * 2 + (max_layer + 1) * (_NODE_W + _H_GAP)
    svg_height = _MARGIN * 2 + max(
        (len(v) * (_NODE_H + _V_GAP)) for v in by_layer.values()
    ) if by_layer else 200

    svg_parts: list[str] = []

    # Draw edges first (so nodes appear on top).
    for edge in graph.edges.values():
        src_key = (edge.from_kind, edge.from_id)
        dst_key = (edge.to_kind, edge.to_id)
        if src_key not in positions or dst_key not in positions:
            continue
        x1, y1 = positions[src_key]
        x2, y2 = positions[dst_key]
        is_cut = (
            edge.from_id in inactive_nodes or edge.from_id in inactive_trans
            or edge.to_id in inactive_nodes or edge.to_id in inactive_trans
        )
        stroke = "#999" if is_cut else "#555"
        dash = 'stroke-dasharray="4 4"' if is_cut else ""
        svg_parts.append(
            f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
            f'stroke="{stroke}" stroke-width="1.5" {dash} marker-end="url(#arrow)"/>'
        )

    # Draw nodes.
    for nid, node in graph.nodes.items():
        key = ("node", nid)
        if key not in positions:
            continue
        cx, cy = positions[key]
        x = cx - _NODE_W / 2
        y = cy - _NODE_H / 2
        is_root = nid == handle.root_node_id
        is_cut = nid in inactive_nodes
        fill = "#ffcc00" if is_root else "#ef4444" if is_cut else "#3b82f6"
        stroke = "#1d4ed8" if not is_cut else "#991b1b"
        label = state_labels.get(nid, "?")
        svg_parts.append(
            f'<rect x="{x:.0f}" y="{y:.0f}" width="{_NODE_W}" height="{_NODE_H}" '
            f'rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )
        svg_parts.append(
            f'<text x="{cx:.0f}" y="{cy + 5:.0f}" text-anchor="middle" '
            f'font-size="13" font-weight="bold" fill="white">{label}</text>'
        )

    # Draw transitions.
    for tid in graph.transitions:
        key = ("transition", tid)
        if key not in positions:
            continue
        cx, cy = positions[key]
        hw = _TRANS_W / 2
        hh = _TRANS_H / 2
        is_cut = tid in inactive_trans
        t_kind = graph.transition_kind(tid)
        fill = "#10b981" if t_kind == "result" else "#06b6d4" if t_kind == "prediction" else "#f59e0b"
        if is_cut:
            fill = "#9ca3af"
        # Diamond shape.
        pts = f"{cx:.0f},{cy - hh:.0f} {cx + hw:.0f},{cy:.0f} {cx:.0f},{cy + hh:.0f} {cx - hw:.0f},{cy:.0f}"
        svg_parts.append(
            f'<polygon points="{pts}" fill="{fill}" stroke="#374151" stroke-width="1.5"/>'
        )
        label = plan_labels.get(tid, "?")
        svg_parts.append(
            f'<text x="{cx:.0f}" y="{cy + 5:.0f}" text-anchor="middle" '
            f'font-size="11" font-weight="bold" fill="white">{label}</text>'
        )

    svg_body = "\n  ".join(svg_parts)
    req = handle.requirement

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>STAG Graph — {handle.run_id}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 16px; }}
  h1 {{ font-size: 1.1rem; margin-bottom: 8px; }}
  .meta {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 16px; }}
  svg {{ display: block; border: 1px solid #334155; border-radius: 8px; background: #1e293b; }}
  .legend {{ display: flex; gap: 16px; margin-top: 12px; font-size: 0.8rem; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .dot {{ width: 12px; height: 12px; border-radius: 2px; }}
</style>
</head>
<body>
<h1>STAG Graph</h1>
<div class="meta">
  Run: {handle.run_id} &nbsp;|&nbsp;
  Target: {req.target_type} / {req.target_id} &nbsp;|&nbsp;
  States: {len(graph.nodes)} &nbsp;|&nbsp;
  Plans: {len(graph.transitions)}
</div>
<svg width="{svg_width:.0f}" height="{svg_height:.0f}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#555"/>
    </marker>
  </defs>
  {svg_body}
</svg>
<div class="legend">
  <div class="legend-item"><div class="dot" style="background:#ffcc00"></div> Root</div>
  <div class="legend-item"><div class="dot" style="background:#3b82f6"></div> State</div>
  <div class="legend-item"><div class="dot" style="background:#10b981"></div> Observed</div>
  <div class="legend-item"><div class="dot" style="background:#06b6d4"></div> Predicted</div>
  <div class="legend-item"><div class="dot" style="background:#f59e0b"></div> Unknown</div>
  <div class="legend-item"><div class="dot" style="background:#9ca3af"></div> Cut</div>
</div>
</body>
</html>"""
