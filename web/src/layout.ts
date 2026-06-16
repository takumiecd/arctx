// Minimal layered DAG layout — no external layout dependency.
//
// Each node's layer = longest path (in steps) from any root. Within a layer,
// nodes are stacked top-to-bottom in discovery order. Good enough for a first
// readable view; a fancier layout (elk/dagre) can replace this behind the same
// {x, y} output if needed.

import type { RunDocument } from "./types";

export interface Pos {
  x: number;
  y: number;
}

const LAYER_GAP = 240;
const ROW_GAP = 90;

export function layout(doc: RunDocument): Record<string, Pos> {
  // parent -> children via steps (input nodes feed the output node).
  const childrenOf = new Map<string, string[]>();
  const indeg = new Map<string, number>();
  for (const n of doc.nodes) indeg.set(n.node_id, 0);
  for (const s of doc.steps) {
    for (const input of s.input_node_ids) {
      if (!childrenOf.has(input)) childrenOf.set(input, []);
      childrenOf.get(input)!.push(s.output_node_id);
      indeg.set(s.output_node_id, (indeg.get(s.output_node_id) ?? 0) + 1);
    }
  }

  // Longest-path layering via Kahn-style relaxation.
  const layer = new Map<string, number>();
  for (const n of doc.nodes) layer.set(n.node_id, 0);
  const queue = doc.nodes.filter((n) => (indeg.get(n.node_id) ?? 0) === 0).map((n) => n.node_id);
  const remaining = new Map(indeg);
  const seen = new Set<string>();
  while (queue.length) {
    const id = queue.shift()!;
    if (seen.has(id)) continue;
    seen.add(id);
    const base = layer.get(id) ?? 0;
    for (const child of childrenOf.get(id) ?? []) {
      layer.set(child, Math.max(layer.get(child) ?? 0, base + 1));
      remaining.set(child, (remaining.get(child) ?? 0) - 1);
      if ((remaining.get(child) ?? 0) <= 0) queue.push(child);
    }
  }

  // Stack nodes within each layer.
  const rowCount = new Map<number, number>();
  const pos: Record<string, Pos> = {};
  for (const n of doc.nodes) {
    const l = layer.get(n.node_id) ?? 0;
    const row = rowCount.get(l) ?? 0;
    rowCount.set(l, row + 1);
    pos[n.node_id] = { x: l * LAYER_GAP, y: row * ROW_GAP };
  }
  return pos;
}
