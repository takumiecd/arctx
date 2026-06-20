// Automatic layout for the first graph view.
//
// arctx steps always produce exactly one output node, so the readable unit is
// usually "producer step + output node". The canvas still renders nodes and
// step edges separately, but initial placement works better when each output
// node reserves vertical space for its downstream branch.

import type { RunDocument } from "./types";

export interface Pos {
  x: number;
  y: number;
}

const LAYER_GAP = 255;
const ROW_GAP = 86;
const MARGIN_X = 48;
const MARGIN_Y = 42;

export function layout(doc: RunDocument): Record<string, Pos> {
  const nodeIds = doc.nodes.map((node) => node.node_id);
  const nodeSet = new Set(nodeIds);
  const nodeOrder = new Map(nodeIds.map((id, index) => [id, index]));
  const children = childrenByInputNode(doc, nodeSet);
  const primaryChildren = primaryChildrenByInputNode(doc, nodeSet);
  const depth = layerDepths(nodeIds, children);
  const span = subtreeSpan(primaryChildren);
  const roots = rootNodes(doc, nodeIds, nodeSet);
  const positions: Record<string, Pos> = {};
  const visited = new Set<string>();
  let nextSlot = 0;

  const place = (nodeId: string, topSlot: number) => {
    if (visited.has(nodeId)) return;
    visited.add(nodeId);

    const ownSpan = span(nodeId);
    positions[nodeId] = {
      x: MARGIN_X + (depth.get(nodeId) ?? 0) * LAYER_GAP,
      y: MARGIN_Y + (topSlot + (ownSpan - 1) / 2) * ROW_GAP,
    };

    let childTop = topSlot;
    for (const childId of sortedChildren(primaryChildren.get(nodeId) ?? [], span, nodeOrder)) {
      place(childId, childTop);
      childTop += span(childId);
    }
  };

  for (const root of roots) {
    if (visited.has(root)) continue;
    place(root, nextSlot);
    nextSlot += span(root) + 1;
  }

  for (const nodeId of nodeIds) {
    if (visited.has(nodeId)) continue;
    place(nodeId, nextSlot);
    nextSlot += span(nodeId) + 1;
  }

  return positions;
}

function childrenByInputNode(doc: RunDocument, nodeSet: Set<string>): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const step of doc.steps) {
    if (!nodeSet.has(step.output_node_id)) continue;
    for (const input of uniqueExistingInputs(step.input_node_ids, nodeSet)) {
      appendUnique(out, input, step.output_node_id);
    }
  }
  return out;
}

function primaryChildrenByInputNode(doc: RunDocument, nodeSet: Set<string>): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const step of doc.steps) {
    if (!nodeSet.has(step.output_node_id)) continue;
    const primaryInput = uniqueExistingInputs(step.input_node_ids, nodeSet)[0];
    if (primaryInput) appendUnique(out, primaryInput, step.output_node_id);
  }
  return out;
}

function layerDepths(nodeIds: string[], children: Map<string, string[]>): Map<string, number> {
  const indegree = new Map(nodeIds.map((id) => [id, 0]));
  const depth = new Map(nodeIds.map((id) => [id, 0]));
  for (const childIds of children.values()) {
    for (const childId of childIds) {
      indegree.set(childId, (indegree.get(childId) ?? 0) + 1);
    }
  }

  const queue = nodeIds.filter((id) => (indegree.get(id) ?? 0) === 0);
  for (let index = 0; index < queue.length; index += 1) {
    const nodeId = queue[index];
    const nextDepth = (depth.get(nodeId) ?? 0) + 1;
    for (const childId of children.get(nodeId) ?? []) {
      depth.set(childId, Math.max(depth.get(childId) ?? 0, nextDepth));
      indegree.set(childId, (indegree.get(childId) ?? 0) - 1);
      if ((indegree.get(childId) ?? 0) === 0) queue.push(childId);
    }
  }

  return depth;
}

function subtreeSpan(primaryChildren: Map<string, string[]>): (nodeId: string) => number {
  const memo = new Map<string, number>();

  const measure = (nodeId: string, visiting = new Set<string>()): number => {
    const cached = memo.get(nodeId);
    if (cached !== undefined) return cached;
    if (visiting.has(nodeId)) return 1;

    visiting.add(nodeId);
    const total = (primaryChildren.get(nodeId) ?? []).reduce(
      (sum, childId) => sum + measure(childId, visiting),
      0,
    );
    visiting.delete(nodeId);

    const value = Math.max(1, total);
    memo.set(nodeId, value);
    return value;
  };

  return measure;
}

function rootNodes(doc: RunDocument, nodeIds: string[], nodeSet: Set<string>): string[] {
  const hasIncoming = new Set<string>();
  for (const step of doc.steps) {
    if (nodeSet.has(step.output_node_id) && uniqueExistingInputs(step.input_node_ids, nodeSet).length > 0) {
      hasIncoming.add(step.output_node_id);
    }
  }

  const roots = nodeIds.filter((id) => !hasIncoming.has(id));
  roots.sort((a, b) => {
    if (a === doc.root_node_id) return -1;
    if (b === doc.root_node_id) return 1;
    return nodeIds.indexOf(a) - nodeIds.indexOf(b);
  });
  return roots.length > 0 ? roots : nodeIds;
}

function uniqueExistingInputs(inputIds: string[], nodeSet: Set<string>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const input of inputIds) {
    if (!nodeSet.has(input) || seen.has(input)) continue;
    seen.add(input);
    out.push(input);
  }
  return out;
}

function sortedChildren(
  childIds: string[],
  span: (nodeId: string) => number,
  nodeOrder: Map<string, number>,
): string[] {
  return [...childIds].sort((a, b) => {
    const spanDiff = span(b) - span(a);
    if (spanDiff !== 0) return spanDiff;
    return (nodeOrder.get(a) ?? 0) - (nodeOrder.get(b) ?? 0);
  });
}

function appendUnique(map: Map<string, string[]>, key: string, value: string) {
  const values = map.get(key);
  if (values) {
    if (!values.includes(value)) values.push(value);
    return;
  }
  map.set(key, [value]);
}
