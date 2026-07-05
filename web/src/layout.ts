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
//
// Two-level clustering: the visible graph is first partitioned into clusters
// -- one per lane, plus a single cluster for unlaned nodes -- and each
// cluster's *internal* subgraph (edges to nodes outside the cluster are
// dropped for placement purposes) is laid out with the layered+serpentine
// algorithm above. Clusters are then packed as non-overlapping blocks,
// ordered chronologically by lane `started_at` (falling back to document
// order when that's missing), flowing left-to-right and wrapping rows at a
// maximum width. Cross-cluster edges (rendered separately in Graph.tsx) may
// end up long as a result; that's an acceptable tradeoff for keeping each
// lane visually together.

import type { RunDocument } from "./types";
import { laneIdForRecord } from "./model";

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

// Cluster (lane block) packing parameters.
const CLUSTER_PADDING = 140; // gap between adjacent cluster boxes
const MAX_ROW_WIDTH = 3000; // wrap to a new row of clusters past this width
const UNLANED_CLUSTER_KEY = "__unlaned__";

interface VisibleGraph {
  nodeIds: string[];
  childrenOf: Map<string, string[]>;
  primaryChildrenOf: Map<string, string[]>;
  parentCountOf: Map<string, number>;
  // The visible endpoint id that the run's root node maps to (itself, or the
  // `lane:<id>` pseudo-node if the root is inside a collapsed lane), or null
  // if the root itself is hidden (cut and showCuts is off).
  rootEndpointId: string | null;
}

export function layout(doc: RunDocument, opts: LayoutOpts): Record<string, Pos> {
  const graph = buildVisibleGraph(doc, opts);
  const clusters = buildClusters(doc, graph);

  const positions: Record<string, Pos> = {};
  let originX = 0;
  let originY = 0;
  let rowHeight = 0;
  let rowWidth = 0;

  for (const cluster of clusters) {
    const { positions: local, width, height } = layoutCluster(cluster, graph);

    if (rowWidth > 0 && rowWidth + CLUSTER_PADDING + width > MAX_ROW_WIDTH) {
      // Wrap to a new row of clusters.
      originX = 0;
      originY += rowHeight + CLUSTER_PADDING;
      rowWidth = 0;
      rowHeight = 0;
    }

    for (const [nodeId, pos] of local) {
      positions[nodeId] = { x: pos.x + originX, y: pos.y + originY };
    }

    rowWidth += width + CLUSTER_PADDING;
    rowHeight = Math.max(rowHeight, height);
    originX += width + CLUSTER_PADDING;
  }

  return positions;
}

// ---------------------------------------------------------------------------
// Clustering: partition visible nodes into lane blocks, ordered chronologically
// ---------------------------------------------------------------------------

interface Cluster {
  key: string;
  nodeIds: string[];
}

// Partition `graph.nodeIds` into one cluster per lane plus one cluster for
// unlaned nodes, ordered chronologically. `doc.lanes` is already sorted by
// `started_at` (falling back to lane_id) server-side (see
// `lane_export_view`), so cluster order simply follows that list; the
// unlaned cluster is inserted at the position of its first member's
// occurrence in document order when nothing else pins it in time.
function buildClusters(doc: RunDocument, graph: VisibleGraph): Cluster[] {
  const memberIds = new Map<string, string[]>();
  const firstIndexOf = new Map<string, number>();

  graph.nodeIds.forEach((nodeId, index) => {
    const key = clusterKeyFor(doc, nodeId);
    const list = memberIds.get(key);
    if (list) {
      list.push(nodeId);
    } else {
      memberIds.set(key, [nodeId]);
      firstIndexOf.set(key, index);
    }
  });

  // `doc.lanes` is already ordered by `started_at` (empty/missing timestamps
  // sort first -- see `lane_export_view`), so a lane cluster's position in
  // that list *is* its chronological rank. The unlaned cluster and any lane
  // id absent from `doc.lanes` (shouldn't normally happen) have no such rank,
  // so they fall back to document order: the index of their first member's
  // appearance in the already-visible node list.
  const laneOrder = new Map((doc.lanes ?? []).map((lane, index) => [lane.lane_id, index]));
  const laneCount = doc.lanes?.length ?? 0;

  const keys = [...memberIds.keys()];
  keys.sort((a, b) => {
    const aRank = laneOrder.get(a) ?? laneCount + (firstIndexOf.get(a) ?? 0);
    const bRank = laneOrder.get(b) ?? laneCount + (firstIndexOf.get(b) ?? 0);
    return aRank - bRank;
  });

  return keys.map((key) => ({ key, nodeIds: memberIds.get(key) ?? [] }));
}

// A visible node id's cluster key: its lane id (via provenance, same source
// `laneIdForRecord` uses for coloring/grouping), or a `lane:<id>` pseudo-node's
// own lane id, or the shared unlaned bucket.
function clusterKeyFor(doc: RunDocument, nodeId: string): string {
  if (nodeId.startsWith("lane:")) return nodeId.slice("lane:".length);
  return laneIdForRecord(doc, nodeId) ?? UNLANED_CLUSTER_KEY;
}

// ---------------------------------------------------------------------------
// Per-cluster layout: the original layered+serpentine algorithm, restricted to
// one cluster's internal subgraph (edges leaving the cluster are dropped).
// ---------------------------------------------------------------------------

function layoutCluster(
  cluster: Cluster,
  graph: VisibleGraph,
): { positions: Map<string, Pos>; width: number; height: number } {
  const members = new Set(cluster.nodeIds);
  const nodeIds = cluster.nodeIds;
  const nodeOrder = new Map(nodeIds.map((id, index) => [id, index]));

  const childrenOf = restrictAdjacency(graph.childrenOf, members);
  const primaryChildrenOf = restrictAdjacency(graph.primaryChildrenOf, members);
  const parentCountOf = restrictParentCounts(nodeIds, childrenOf);

  const depth = layerDepths(nodeIds, childrenOf);
  const span = subtreeSpan(primaryChildrenOf);
  const rootEndpointId = members.has(graph.rootEndpointId ?? "") ? graph.rootEndpointId : null;
  const roots = rootNodes(nodeIds, parentCountOf, rootEndpointId);

  const positions = new Map<string, Pos>();
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

      positions.set(currentId, { x, y });

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

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const pos of positions.values()) {
    minX = Math.min(minX, pos.x);
    minY = Math.min(minY, pos.y);
    maxX = Math.max(maxX, pos.x);
    maxY = Math.max(maxY, pos.y);
  }

  // Normalize so every cluster's box starts at the same local origin
  // (MARGIN_X, MARGIN_Y): a cluster's internal placement can start its
  // topmost/leftmost member above/left of the nominal margin depending on
  // its branch shape, and without this the packer's shared row baseline
  // (`originY`) would not actually line clusters' top edges up.
  const shiftX = MARGIN_X - minX;
  const shiftY = MARGIN_Y - minY;
  if (shiftX !== 0 || shiftY !== 0) {
    for (const [nodeId, pos] of positions) {
      positions.set(nodeId, { x: pos.x + shiftX, y: pos.y + shiftY });
    }
  }

  // Approximate a node's footprint past its anchor point so the bounding box
  // (used for packing, not rendering) doesn't clip the last column/row.
  const width = maxX - minX + MARGIN_X + LAYER_GAP;
  const height = maxY - minY + MARGIN_Y + ROW_GAP * 2;

  return { positions, width, height };
}

function restrictAdjacency(
  adjacency: Map<string, string[]>,
  members: Set<string>,
): Map<string, string[]> {
  const restricted = new Map<string, string[]>();
  for (const [source, targets] of adjacency) {
    if (!members.has(source)) continue;
    const kept = targets.filter((target) => members.has(target));
    if (kept.length > 0) restricted.set(source, kept);
  }
  return restricted;
}

function restrictParentCounts(
  nodeIds: string[],
  childrenOf: Map<string, string[]>,
): Map<string, number> {
  const counts = new Map(nodeIds.map((id) => [id, 0]));
  for (const targets of childrenOf.values()) {
    for (const target of targets) {
      counts.set(target, (counts.get(target) ?? 0) + 1);
    }
  }
  return counts;
}

// Build the visible node-id list and adjacency maps: inactive nodes dropped
// (unless showCuts), collapsed-lane members contracted into `lane:<id>`
// pseudo-nodes. Steps whose endpoints map to the same pseudo-node (i.e. both
// endpoints are inside the same collapsed lane) are dropped; other steps
// become edges between the mapped endpoints.
function buildVisibleGraph(doc: RunDocument, opts: LayoutOpts): VisibleGraph {
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
