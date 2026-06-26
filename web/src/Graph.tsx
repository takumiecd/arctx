// React Flow view of a run. Nodes = arctx Nodes; edges = arctx Steps
// (one edge per input -> output, labeled with the step's payload type).
//
// Creating steps by dragging (the arctx rule: a step always has a single
// output node):
//   - drag from a node handle and release on empty canvas -> new output node
//   - drag onto an existing producer-less node            -> that node becomes
//                                                             the step's output
//   - shift-select several nodes first                    -> multi-input step
//
// Cut/inactive records are dimmed. Selecting exactly one node or one edge
// drives the detail panel.

import { useCallback, useEffect, useRef, type CSSProperties } from "react";
import {
  Background,
  ConnectionMode,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type FinalConnectionState,
  MarkerType,
  type Node,
  type NodeProps,
  type OnSelectionChangeParams,
  SelectionMode,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { layout, type Pos } from "./layout";
import {
  laneColors,
  laneGroups,
  laneIdForRecord,
  laneLabel,
  nodeLabel,
  nodeSummaryText,
  stepType,
  type LaneColorOverrides,
} from "./model";
import type { RunDocument, RunGroup } from "./types";

export type Selection =
  | { kind: "node"; id: string }
  | { kind: "step"; id: string }
  | { kind: "lane"; id: string }
  | { kind: "records"; records: { kind: "node" | "step"; id: string }[] }
  | null;

// Custom node with source/target handles on each side. ConnectionMode.Loose
// keeps dragging ergonomic while fixed handle IDs let rendered edges enter the
// side that matches graph direction.
function DagNode({ data }: NodeProps) {
  const d = data as {
    label: string;
    title: string;
    isRoot: boolean;
    inactive: boolean;
    summaryText?: string;
    laneLabel?: string;
    laneColor?: string;
    laneBg?: string;
  };
  const sides = [
    ["top", Position.Top],
    ["right", Position.Right],
    ["bottom", Position.Bottom],
    ["left", Position.Left],
  ] as const;
  return (
    <div
      className={`dag-node${d.isRoot ? " root" : ""}${d.inactive ? " inactive" : ""}${d.laneColor ? " lane" : ""}`}
      title={d.title}
      style={laneStyle(d)}
    >
      {sides.map(([id, p]) => (
        <Handle key={`source-${id}`} type="source" position={p} id={id} />
      ))}
      {sides.map(([id, p]) => (
        <Handle key={`target-${id}`} type="target" position={p} id={id} />
      ))}
      {d.laneLabel && <em>{d.laneLabel}</em>}
      <span>{d.label}</span>
      {d.summaryText && (
        <span
          title={`summary: ${d.summaryText}`}
          style={{
            position: "absolute",
            top: -8,
            right: -6,
            fontSize: 9,
            lineHeight: "12px",
            padding: "0 4px",
            borderRadius: 6,
            background: "#7c3aed",
            color: "#fff",
            pointerEvents: "none",
          }}
        >
          ✦
        </span>
      )}
    </div>
  );
}

function LaneGroupNode({ data }: NodeProps) {
  const d = data as { label: string; laneColor: string; laneBg: string };
  return (
    <div className="lane-group-box" style={laneStyle(d)}>
      <span>{d.label}</span>
    </div>
  );
}

function LaneCollapsedNode({ data }: NodeProps) {
  const d = data as {
    label: string;
    title: string;
    laneColor: string;
    laneBg: string;
    nodeCount: number;
    stepCount: number;
    summaryCount: number;
  };
  const sides = [
    ["top", Position.Top],
    ["right", Position.Right],
    ["bottom", Position.Bottom],
    ["left", Position.Left],
  ] as const;
  return (
    <div className="lane-collapsed-node" title={d.title} style={laneStyle(d)}>
      {sides.map(([id, p]) => (
        <Handle key={`source-${id}`} type="source" position={p} id={id} isConnectable={false} />
      ))}
      {sides.map(([id, p]) => (
        <Handle key={`target-${id}`} type="target" position={p} id={id} isConnectable={false} />
      ))}
      <strong>{d.label}</strong>
      <span>
        {d.nodeCount} nodes · {d.stepCount} steps
      </span>
      {d.summaryCount > 0 && <span>{d.summaryCount} summaries</span>}
    </div>
  );
}

const nodeTypes = { dag: DagNode, laneGroup: LaneGroupNode, laneCollapsed: LaneCollapsedNode };
const NODE_WIDTH = 150;
const NODE_HEIGHT = 58;
const LANE_GROUP_PADDING_X = 42;
const LANE_GROUP_PADDING_TOP = 44;
const LANE_GROUP_PADDING_BOTTOM = 34;

interface Props {
  doc: RunDocument;
  savedNodePositions: Record<string, Pos>;
  onSelect: (sel: Selection) => void;
  onNodePositionsChanged: (positions: Record<string, Pos>) => void;
  onCreateStep: (
    inputNodeIds: string[],
    outputNodeId?: string,
  ) => Promise<{ outputNodeId: string } | void>;
  onRunChanged: () => void;
  collapsedLaneIds: Set<string>;
  onToggleLane: (laneId: string) => void;
  laneColorOverrides: LaneColorOverrides;
  writable: boolean;
  showCuts: boolean;
  dark: boolean;
}

type Side = "top" | "right" | "bottom" | "left";

function laneStyle(data: { laneColor?: string; laneBg?: string }): CSSProperties {
  return {
    "--lane-color": data.laneColor,
    "--lane-bg": data.laneBg,
  } as CSSProperties;
}

function edgeSides(source: Pos | undefined, target: Pos | undefined): [Side, Side] {
  if (!source || !target) return ["right", "left"];

  const dx = target.x - source.x;

  // Keep graph edges in the reading direction. Vertical top/bottom edges make
  // sibling branches look like a serial chain when the layout stacks them.
  return dx >= 0 ? ["right", "left"] : ["left", "right"];
}

function buildEdges(
  doc: RunDocument,
  positions: Record<string, Pos>,
  collapsedLaneIds: Set<string>,
  laneColorOverrides: LaneColorOverrides,
  showCuts: boolean,
  dark: boolean,
): Edge[] {
  const out: Edge[] = [];
  const inactiveNodeIds = new Set(
    doc.nodes.filter((n) => n.inactive).map((n) => n.node_id)
  );

  for (const s of doc.steps) {
    if (!showCuts && s.inactive) continue;

    const stepLaneId = laneIdForRecord(doc, s.step_id) ?? laneIdForRecord(doc, s.output_node_id);
    const laneColor = stepLaneId
      ? laneColors(doc, stepLaneId, laneColorOverrides, dark).laneColor
      : "#475569";
    const edgeColor = s.inactive ? "#94a3b8" : laneColor;
    const label = stepType(doc, s.step_id);
    for (const input of s.input_node_ids) {
      if (!showCuts && (inactiveNodeIds.has(input) || inactiveNodeIds.has(s.output_node_id))) {
        continue;
      }

      const source = endpointFor(doc, input, collapsedLaneIds);
      const target = endpointFor(doc, s.output_node_id, collapsedLaneIds);
      if (source === target) continue;
      const [sourceHandle, targetHandle] = edgeSides(positions[source], positions[target]);
      out.push({
        id: `${s.step_id}:${input}:${source}->${target}`,
        source,
        target,
        sourceHandle,
        targetHandle,
        type: "smoothstep",
        label: label === "step" ? undefined : label,
        data: { stepId: s.step_id },
        labelStyle: { fontSize: 11 },
        labelBgPadding: [6, 3],
        labelBgBorderRadius: 4,
        style: {
          opacity: s.inactive ? 0.35 : 1,
          stroke: edgeColor,
          strokeWidth: stepLaneId ? 2.4 : 1.8,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: edgeColor,
          width: 16,
          height: 16,
        },
      });
    }
  }
  return out;
}

function endpointFor(doc: RunDocument, nodeId: string, collapsedLaneIds: Set<string>): string {
  const laneId = laneIdForRecord(doc, nodeId);
  return laneId && collapsedLaneIds.has(laneId) ? `lane:${laneId}` : nodeId;
}

function laneBounds(
  group: RunGroup,
  positions: Map<string, Pos>,
): { x: number; y: number; width: number; height: number } | null {
  const memberPositions = group.node_ids
    .map((nodeId) => positions.get(nodeId))
    .filter((p): p is Pos => Boolean(p));
  if (memberPositions.length === 0) return null;
  const minX = Math.min(...memberPositions.map((p) => p.x));
  const minY = Math.min(...memberPositions.map((p) => p.y));
  const maxX = Math.max(...memberPositions.map((p) => p.x + NODE_WIDTH));
  const maxY = Math.max(...memberPositions.map((p) => p.y + NODE_HEIGHT));
  return {
    x: minX - LANE_GROUP_PADDING_X,
    y: minY - LANE_GROUP_PADDING_TOP,
    width: maxX - minX + LANE_GROUP_PADDING_X * 2,
    height: maxY - minY + LANE_GROUP_PADDING_TOP + LANE_GROUP_PADDING_BOTTOM,
  };
}

function eventClientPosition(event: MouseEvent | TouchEvent): Pos | null {
  if ("clientX" in event) {
    return { x: event.clientX, y: event.clientY };
  }
  const touch = event.changedTouches[0] ?? event.touches[0];
  return touch ? { x: touch.clientX, y: touch.clientY } : null;
}

function GraphCanvas({
  doc,
  savedNodePositions,
  onSelect,
  onNodePositionsChanged,
  onCreateStep,
  onRunChanged,
  collapsedLaneIds,
  onToggleLane,
  laneColorOverrides,
  writable,
  showCuts,
  dark,
}: Props) {
  const reactFlow = useReactFlow<Node, Edge>();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // The node the current connection drag started from, and the live multi-node
  // selection (used as step inputs when several nodes are selected).
  const dragSource = useRef<string | null>(null);
  const selectedNodeIds = useRef<string[]>([]);
  const pendingNodePositions = useRef<Map<string, Pos>>(new Map());

  // Rebuild from the run document, preserving manual positions and selection
  // across polled refetches so the canvas doesn't jump.
  useEffect(() => {
    const pos = layout(doc);
    setNodes((prev) => {
      const prevPos = new Map(prev.map((n) => [n.id, n.position]));
      const prevSel = new Map(prev.map((n) => [n.id, n.selected]));
      const resolvedPositions = new Map<string, Pos>();
      for (const n of doc.nodes) {
        if (!showCuts && n.inactive) continue;
        const pendingPos = pendingNodePositions.current.get(n.node_id);
        if (pendingPos) {
          pendingNodePositions.current.delete(n.node_id);
        }
        resolvedPositions.set(
          n.node_id,
          pendingPos ??
            savedNodePositions[n.node_id] ??
            prevPos.get(n.node_id) ??
            pos[n.node_id] ??
            { x: 0, y: 0 },
        );
      }

      const groups = laneGroups(doc);
      const nextNodes: Node[] = [];

      for (const group of groups) {
        if (!group.lane_id || collapsedLaneIds.has(group.lane_id)) continue;
        const box = laneBounds(group, resolvedPositions);
        if (!box) continue;
        const colors = laneColors(doc, group.lane_id, laneColorOverrides, dark);
        nextNodes.push({
          id: group.group_id,
          type: "laneGroup",
          position: { x: box.x, y: box.y },
          data: { label: group.label, ...colors },
          draggable: false,
          selectable: false,
          zIndex: 0,
          style: { width: box.width, height: box.height },
        });
      }

      for (const group of groups) {
        if (!group.lane_id || !collapsedLaneIds.has(group.lane_id)) continue;
        const collapsedId = `lane:${group.lane_id}`;
        const box = laneBounds(group, resolvedPositions);
        const colors = laneColors(doc, group.lane_id, laneColorOverrides, dark);
        nextNodes.push({
          id: collapsedId,
          type: "laneCollapsed",
          position:
            savedNodePositions[collapsedId] ??
            prevPos.get(collapsedId) ??
            (box ? { x: box.x + box.width / 2 - 70, y: box.y + box.height / 2 - 30 } : { x: 0, y: 0 }),
          selected: prevSel.get(collapsedId) ?? false,
          data: {
            label: group.label,
            title: `lane ${group.label} (click for summaries, double-click to expand)`,
            nodeCount: group.node_ids.length,
            stepCount: group.step_ids.length,
            summaryCount: (doc.lane_edge_summaries ?? []).filter(
              (summary) => summary.lane_id === group.lane_id,
            ).length,
            ...colors,
          },
          zIndex: 2,
        });
      }

      for (const n of doc.nodes) {
        if (!showCuts && n.inactive) continue;
        const laneId = laneIdForRecord(doc, n.node_id);
        if (laneId && collapsedLaneIds.has(laneId)) continue;
        const colors = laneId ? laneColors(doc, laneId, laneColorOverrides, dark) : {};
        const label = laneId ? laneLabel(doc, laneId) : undefined;
        nextNodes.push({
          id: n.node_id,
          type: "dag",
          position: resolvedPositions.get(n.node_id) ?? { x: 0, y: 0 },
          selected: prevSel.get(n.node_id) ?? false,
          data: {
            label: nodeLabel(doc, n.node_id),
            title: n.node_id,
            isRoot: n.node_id === doc.root_node_id,
            inactive: n.inactive,
            summaryText: nodeSummaryText(doc, n.node_id) ?? undefined,
            laneLabel: label,
            ...colors,
          },
          zIndex: 2,
        });
      }

      return nextNodes;
    });
  }, [collapsedLaneIds, dark, doc, laneColorOverrides, savedNodePositions, setNodes, showCuts]);

  // Edge paths should follow where nodes actually are, including after a user
  // drags nodes around. Use the nearest side instead of letting React Flow
  // default every target toward the top.
  useEffect(() => {
    const fallbackPos = layout(doc);
    const positions: Record<string, Pos> = { ...fallbackPos };
    for (const n of nodes) {
      positions[n.id] = n.position;
    }
    setEdges(buildEdges(doc, positions, collapsedLaneIds, laneColorOverrides, showCuts, dark));
  }, [collapsedLaneIds, dark, doc, laneColorOverrides, nodes, setEdges, showCuts]);

  const inputsFor = (source: string | null): string[] => {
    if (!source) return [];
    const sel = selectedNodeIds.current;
    return sel.length > 1 && sel.includes(source) ? sel : [source];
  };

  const onSelectionChange = useCallback(
    ({ nodes: ns, edges: es }: OnSelectionChangeParams) => {
      selectedNodeIds.current = ns.map((n) => n.id);
      if (ns.length === 1 && es.length === 0) {
        const nodeId = ns[0].id;
        if (nodeId.startsWith("lane:")) {
          onSelect({ kind: "lane", id: nodeId.slice("lane:".length) });
        } else {
          onSelect({ kind: "node", id: nodeId });
        }
      } else if (es.length === 1 && ns.length === 0) {
        onSelect({ kind: "step", id: (es[0].data as { stepId: string }).stepId });
      } else if (ns.length + es.length > 1) {
        const records = [
          ...ns
            .filter((node) => !node.id.startsWith("lane:"))
            .map((node) => ({ kind: "node" as const, id: node.id })),
          ...es.map((edge) => ({
            kind: "step" as const,
            id: (edge.data as { stepId: string }).stepId,
          })),
        ];
        if (records.length > 0) {
          onSelect({ kind: "records", records });
        } else {
          onSelect(null);
        }
      } else {
        onSelect(null);
      }
    },
    [onSelect],
  );

  // Dropped onto an existing node -> connect into it (it becomes the output).
  const onConnect = useCallback(
    (c: Connection) => {
      if (c.source && c.target && c.source !== c.target) {
        void onCreateStep(inputsFor(c.source), c.target)
          .then(() => onRunChanged())
          .catch(() => undefined);
      }
    },
    [onCreateStep, onRunChanged],
  );

  const onConnectStart = useCallback(
    (_: unknown, params: { nodeId: string | null }) => {
      dragSource.current = params.nodeId;
    },
    [],
  );

  // Dropped on empty canvas (no target node) -> mint a new output node.
  const onConnectEnd = useCallback(
    async (event: MouseEvent | TouchEvent, state: FinalConnectionState) => {
      if (!state.toNode && dragSource.current) {
        const clientPosition = eventClientPosition(event);
        const flowPosition = clientPosition
          ? reactFlow.screenToFlowPosition(clientPosition)
          : null;
        try {
          const result = await onCreateStep(inputsFor(dragSource.current));
          if (result?.outputNodeId && flowPosition) {
            pendingNodePositions.current.set(result.outputNodeId, {
              x: flowPosition.x - NODE_WIDTH / 2,
              y: flowPosition.y - NODE_HEIGHT / 2,
            });
          }
          onRunChanged();
        } catch {
          // The mutation stores the error for the header; avoid an unhandled
          // rejection from the event callback.
        }
      }
      dragSource.current = null;
    },
    [onCreateStep, onRunChanged, reactFlow],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeDragStop={
        writable
          ? (_event, _node, ns) =>
              onNodePositionsChanged(
                Object.fromEntries(
                  ns
                    .filter((node) => node.type !== "laneGroup")
                    .map((node) => [node.id, node.position]),
                ),
              )
          : undefined
      }
      onNodeDoubleClick={(_event, node) => {
        if (node.id.startsWith("lane:")) onToggleLane(node.id.slice("lane:".length));
      }}
      onSelectionChange={onSelectionChange}
      onConnect={writable ? onConnect : undefined}
      onConnectStart={writable ? onConnectStart : undefined}
      onConnectEnd={writable ? onConnectEnd : undefined}
      nodesConnectable={writable}
      connectionMode={ConnectionMode.Loose}
      panOnScroll={true}
      panOnScrollSpeed={1.2}
      zoomOnScroll={false}
      zoomActivationKeyCode="Control"
      panOnDrag={true}
      selectionOnDrag={false}
      multiSelectionKeyCode="Shift"
      selectionMode={SelectionMode.Partial}
      fitView
      proOptions={{ hideAttribution: true }}
    >
      <Background color={document.documentElement.getAttribute("data-theme") === "dark" ? "#334155" : undefined} />
      <Controls />
    </ReactFlow>
  );
}

export function Graph(props: Props) {
  return (
    <ReactFlowProvider>
      <GraphCanvas {...props} />
    </ReactFlowProvider>
  );
}
