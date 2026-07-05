// Automatic layout for the graph view.
//
// arctx steps always produce exactly one output node, so the readable unit is
// usually "producer step + output node". The canvas still renders nodes and
// step edges separately, but placement works better when each output node
// reserves vertical space for its downstream branch.
//
// Layout operates on the VISIBLE graph, not the full document: inactive
// (cut) nodes are dropped when `showCuts` is false, and members of a
// collapsed lane are contracted into a single `lane:<laneId>` pseudo-node
// (the same convention `endpointFor` in Graph.tsx uses for rendering). This
// keeps the canvas compact instead of leaving empty holes where the full
// graph would have placed hidden members.
//
// Long, purely linear chains (each node has exactly one primary child, and
// that child has exactly one parent) are wrapped into a boustrophedon
// (serpentine) ribbon after a handful of layers, instead of running off the
// canvas as one long horizontal string.

import type { RunDocument } from "./types";

export interface Pos {
  x: number;
  y: number;
}

export interface LayoutOpts {
  collapsedLaneIds: Set<string>;
  showCuts: boolean;
}

const LAYER_GAP = 200;
const ROW_GAP = 86;
const MARGIN_X = 48;
const MARGIN_Y = 42;

// After this many consecutive layers, a purely linear chain wraps to the next
// row instead of continuing to extend horizontally.
const CHAIN_WRAP_LENGTH = 7;

export function layout(doc: RunDocument, opts: LayoutOpts): Record<string, Pos> {
  const { nodeIds, childrenOf, primaryChildrenOf, parentCountOf, rootEndpointId } = buildVisibleGraph(doc, opts);

  const nodeOrder = new Map(nodeIds.map((id, index) => [id, index]));
  const depth = layerDepths(nodeIds, childrenOf);
  const span = subtreeSpan(primaryChildrenOf);
  const roots = rootNodes(nodeIds, parentCountOf, rootEndpointId);
  const positions: Record<string, Pos> = {};
  const visited = new Set<string>();
  let nextSlot = 0;

  const place = (nodeId: string, topSlot: number) => {
    if (visited.has(nodeId)) return;

    // Walk forward along a purely linear chain starting at nodeId, placing
    // each member on a serpentine ribbon: every CHAIN_WRAP_LENGTH layers,
    // wrap to the next row and reverse horizontal direction. A chain of
    // length 1 (no wrapping needed) degenerates to the plain single-layer
    // placement below. The chain's starting column follows nodeId's real
    // graph depth so it lines up with sibling branches placed elsewhere.
    const baseDepth = depth.get(nodeId) ?? 0;
    let chainId: string | null = nodeId;
    let chainIndex = 0;
    const rowSlot = topSlot + (span(nodeId) - 1) / 2;

    while (chainId !== null) {
      const currentId: string = chainId;
      visited.add(currentId);

      const wrapRow = Math.floor(chainIndex / CHAIN_WRAP_LENGTH);
      const posInRow = chainIndex % CHAIN_WRAP_LENGTH;
      // Alternate direction each wrapped row (boustrophedon): even rows go
      // left-to-right, odd rows go right-to-left.
      const rowDirection = wrapRow % 2 === 0 ? 1 : -1;
      const colInRow =
        wrapRow === 0
          ? baseDepth + posInRow
          : rowDirection === 1
            ? posInRow
            : CHAIN_WRAP_LENGTH - 1 - posInRow;
      const x = MARGIN_X + colInRow * LAYER_GAP;
      const y = MARGIN_Y + (rowSlot + wrapRow * 1.35) * ROW_GAP;

      positions[currentId] = { x, y };

      const nextChildren: string[] = primaryChildrenOf.get(currentId) ?? [];
      const child: string | undefined = nextChildren[0];
      const chainContinues =
        child !== undefined && !visited.has(child) && (parentCountOf.get(child) ?? 0) === 1;

      if (!chainContinues) {
        // Chain ended (branch, merge, or leaf). Recurse normally into any
        // children from here (covers branching at the chain's tail).
        let childTop = topSlot;
        for (const childId of sortedChildren(nextChildren, span, nodeOrder)) {
          place(childId, childTop);
          childTop += span(childId);
        }
        chainId = null;
        break;
      }

      chainId = child;
      chainIndex += 1;
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

// Build the visible node-id list and adjacency maps: inactive nodes dropped
// (unless showCuts), collapsed-lane members contracted into `lane:<id>`
// pseudo-nodes. Steps whose endpoints map to the same pseudo-node (i.e. both
// endpoints are inside the same collapsed lane) are dropped; other steps
// become edges between the mapped endpoints.
function buildVisibleGraph(
  doc: RunDocument,
  opts: LayoutOpts,
): {
  nodeIds: string[];
  childrenOf: Map<string, string[]>;
  primaryChildrenOf: Map<string, string[]>;
  parentCountOf: Map<string, number>;
  // The visible endpoint id that the run's root node maps to (itself, or the
  // `lane:<id>` pseudo-node if the root is inside a collapsed lane), or null
  // if the root itself is hidden (cut and showCuts is off).
  rootEndpointId: string | null;
} {
  const { collapsedLaneIds, showCuts } = opts;

  const laneIdByNode = new Map<string, string>();
  for (const group of doc.groups ?? []) {
    if (group.kind !== "lane" || !group.lane_id) continue;
    if (!collapsedLaneIds.has(group.lane_id)) continue;
    for (const nodeId of group.node_ids) {
      laneIdByNode.set(nodeId, group.lane_id);
    }
  }

  const activeNodeIds = new Set(
    doc.nodes.filter((n) => showCuts || !n.inactive).map((n) => n.node_id),
  );

  const endpoint = (nodeId: string): string | null => {
    if (!activeNodeIds.has(nodeId)) return null;
    const laneId = laneIdByNode.get(nodeId);
    return laneId ? `lane:${laneId}` : nodeId;
  };

  // Visible node id list: real visible nodes not in a collapsed lane, plus one
  // pseudo-node per collapsed lane that has at least one visible member.
  const nodeIds: string[] = [];
  const seenPseudo = new Set<string>();
  for (const n of doc.nodes) {
    if (!activeNodeIds.has(n.node_id)) continue;
    const laneId = laneIdByNode.get(n.node_id);
    if (laneId) {
      const pseudoId = `lane:${laneId}`;
      if (!seenPseudo.has(pseudoId)) {
        seenPseudo.add(pseudoId);
        nodeIds.push(pseudoId);
      }
      continue;
    }
    nodeIds.push(n.node_id);
  }

  const childrenOf = new Map<string, string[]>();
  const primaryChildrenOf = new Map<string, string[]>();
  const parentCountOf = new Map<string, number>();

  for (const step of doc.steps) {
    if (!showCuts && step.inactive) continue;
    const target = endpoint(step.output_node_id);
    if (!target) continue;

    const sources: string[] = [];
    const seenSource = new Set<string>();
    for (const inputId of step.input_node_ids) {
      const source = endpoint(inputId);
      if (!source || source === target || seenSource.has(source)) continue;
      seenSource.add(source);
      sources.push(source);
    }
    if (sources.length === 0) continue;

    parentCountOf.set(target, (parentCountOf.get(target) ?? 0) + sources.length);
    for (const source of sources) {
      appendUnique(childrenOf, source, target);
    }
    appendUnique(primaryChildrenOf, sources[0], target);
  }

  return { nodeIds, childrenOf, primaryChildrenOf, parentCountOf, rootEndpointId: endpoint(doc.root_node_id) };
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

function rootNodes(
  nodeIds: string[],
  parentCountOf: Map<string, number>,
  rootEndpointId: string | null,
): string[] {
  const hasIncoming = new Set(
    [...parentCountOf.entries()].filter(([, count]) => count > 0).map(([id]) => id),
  );

  const roots = nodeIds.filter((id) => !hasIncoming.has(id));
  roots.sort((a, b) => {
    const aIsRoot = a === rootEndpointId;
    const bIsRoot = b === rootEndpointId;
    if (aIsRoot && !bIsRoot) return -1;
    if (bIsRoot && !aIsRoot) return 1;
    return nodeIds.indexOf(a) - nodeIds.indexOf(b);
  });
  return roots.length > 0 ? roots : nodeIds;
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
