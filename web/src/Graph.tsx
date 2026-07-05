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

import { useCallback, useEffect, useRef, type CSSProperties, type RefObject } from "react";
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
  useUpdateNodeInternals,
  useReactFlow,
  useStore,
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
  laneStatus,
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

// A nonce-carrying request to focus the viewport on a lane. Bump `ts` even
// when re-selecting the same lane so the effect fires again.
export interface LaneFocusRequest {
  laneId: string;
  ts: number;
}

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
        <Handle key={`source-${id}`} type="source" position={p} id={`source-${id}`} />
      ))}
      {sides.map(([id, p]) => (
        <Handle key={`target-${id}`} type="target" position={p} id={`target-${id}`} />
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
    status?: "open" | "closed";
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
        <Handle
          key={`source-${id}`}
          type="source"
          position={p}
          id={`source-${id}`}
          isConnectable={false}
        />
      ))}
      {sides.map(([id, p]) => (
        <Handle
          key={`target-${id}`}
          type="target"
          position={p}
          id={`target-${id}`}
          isConnectable={false}
        />
      ))}
      <strong>{d.label}</strong>
      {d.status === "closed" && <span className="lane-status-badge closed">closed</span>}
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

// Below this zoom level, edge labels and per-node lane chips are hidden (see
// ZoomDeclutter below) -- at this scale they're mostly noise, not information.
const ZOOMED_OUT_THRESHOLD = 0.45;

// Toggles a "zoomed-out" class on the ReactFlow wrapper based on the current
// viewport zoom. Subscribing to the raw transform would re-render on every
// pan/zoom tick; instead this selects a boolean derived from the zoom level,
// so React only re-renders when the value actually flips across the
// threshold (avoids a per-node re-render storm while zooming).
function ZoomDeclutter({ containerRef }: { containerRef: RefObject<HTMLDivElement | null> }) {
  const isZoomedOut = useStore((s) => s.transform[2] < ZOOMED_OUT_THRESHOLD);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.classList.toggle("zoomed-out", isZoomedOut);
  }, [containerRef, isZoomedOut]);
  return null;
}

interface Props {
  doc: RunDocument;
  selection: Selection | null;
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
  focusLane?: LaneFocusRequest | null;
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
      const inputLaneId = laneIdForRecord(doc, input);
      const outputLaneId = laneIdForRecord(doc, s.output_node_id);
      const crossLane = inputLaneId !== outputLaneId;
      const [sourceHandle, targetHandle] = edgeSides(positions[source], positions[target]);
      out.push({
        id: edgeId(s.step_id, input, source, target),
        source,
        target,
        sourceHandle: `source-${sourceHandle}`,
        targetHandle: `target-${targetHandle}`,
        type: crossLane ? "simplebezier" : "smoothstep",
        label: crossLane || label === "step" ? undefined : label,
        data: { stepId: s.step_id },
        selectable: false,
        labelStyle: { fontSize: 11 },
        labelBgPadding: [6, 3],
        labelBgBorderRadius: 4,
        style: {
          opacity: s.inactive ? 0.35 : crossLane ? 0.55 : 1,
          stroke: edgeColor,
          strokeDasharray: crossLane ? "5 6" : undefined,
          strokeWidth: crossLane ? 1.5 : stepLaneId ? 2.4 : 1.8,
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

function edgeId(stepId: string, inputId: string, sourceId: string, targetId: string): string {
  const parts = [stepId, inputId, sourceId, targetId].map(safeEdgePart);
  return `edge_${parts.join("_")}`;
}

function safeEdgePart(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, "_");
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
  selection,
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
  focusLane,
}: Props) {
  const reactFlow = useReactFlow<Node, Edge>();
  const updateNodeInternals = useUpdateNodeInternals();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  // The node the current connection drag started from, and the live multi-node
  // selection (used as step inputs when several nodes are selected).
  const dragSource = useRef<string | null>(null);
  const selectedNodeIds = useRef<string[]>([]);
  const ignoreNextEmptySelection = useRef(false);
  const pendingNodePositions = useRef<Map<string, Pos>>(new Map());

  // The serialized (collapsedLaneIds, showCuts) key from the last render.
  // `prevPos` (previous on-screen position) exists so polled refetches don't
  // make the canvas jump around; but when what's *visible* changes, the fresh
  // auto-layout should win instead, otherwise collapsing a lane or hiding
  // cuts leaves everything else at its old, now-sparse position.
  const lastVisibilityKeyRef = useRef<string | null>(null);

  // Rebuild from the run document, preserving manual positions and selection
  // across polled refetches so the canvas doesn't jump.
  useEffect(() => {
    const pos = layout(doc, { collapsedLaneIds, showCuts });
    const visibilityKey = `${[...collapsedLaneIds].sort().join(",")}|${showCuts}`;
    const visibilityChanged = lastVisibilityKeyRef.current !== null && lastVisibilityKeyRef.current !== visibilityKey;
    lastVisibilityKeyRef.current = visibilityKey;

    setNodes((prev) => {
      const prevPos = new Map(prev.map((n) => [n.id, n.position]));
      const prevSel = new Map(prev.map((n) => [n.id, n.selected]));
      const resolvedPositions = new Map<string, Pos>();

      // Position precedence: pendingNodePositions (just-created via drag) >
      // savedNodePositions (manual, persisted) > fresh layout (when
      // visibility changed) > prevPos (on-screen position, kept across
      // polled refetches) > fresh layout (fallback) > origin.
      const resolve = (id: string): Pos => {
        const pendingPos = pendingNodePositions.current.get(id);
        if (pendingPos) {
          pendingNodePositions.current.delete(id);
          return pendingPos;
        }
        if (savedNodePositions[id]) return savedNodePositions[id];
        if (visibilityChanged && pos[id]) return pos[id];
        return prevPos.get(id) ?? pos[id] ?? { x: 0, y: 0 };
      };

      for (const n of doc.nodes) {
        if (!showCuts && n.inactive) continue;
        const laneId = laneIdForRecord(doc, n.node_id);
        if (laneId && collapsedLaneIds.has(laneId)) continue;
        resolvedPositions.set(n.node_id, resolve(n.node_id));
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
        // The pseudo-node position comes straight from the layout, which
        // treats the collapsed lane as a single slot — this is what keeps
        // the collapsed card from sitting in the middle of the hole left by
        // its (now hidden) expanded bounds.
        const collapsedPos = resolve(collapsedId);
        resolvedPositions.set(collapsedId, collapsedPos);
        const colors = laneColors(doc, group.lane_id, laneColorOverrides, dark);
        nextNodes.push({
          id: collapsedId,
          type: "laneCollapsed",
          position: collapsedPos,
          selected: prevSel.get(collapsedId) ?? false,
          data: {
            label: group.label,
            title: `lane ${group.label} (click for summaries, double-click to expand)`,
            nodeCount: group.node_ids.length,
            stepCount: group.step_ids.length,
            summaryCount: (doc.lane_edge_summaries ?? []).filter(
              (summary) => summary.lane_id === group.lane_id,
            ).length,
            status: laneStatus(doc, group.lane_id),
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
    const fallbackPos = layout(doc, { collapsedLaneIds, showCuts });
    const positions: Record<string, Pos> = { ...fallbackPos };
    for (const n of nodes) {
      positions[n.id] = n.position;
    }
    const nextEdges = buildEdges(doc, positions, collapsedLaneIds, laneColorOverrides, showCuts, dark);
    setEdges(nextEdges);
  }, [collapsedLaneIds, dark, doc, laneColorOverrides, nodes, setEdges, showCuts]);

  useEffect(() => {
    if (nodes.length === 0) return;
    const frame = window.requestAnimationFrame(() => {
      for (const node of nodes) {
        updateNodeInternals(node.id);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [nodes, updateNodeInternals]);

  useEffect(() => {
    const targetSelectedNodes = new Set<string>();
    if (selection) {
      if (selection.kind === "node") targetSelectedNodes.add(selection.id);
      else if (selection.kind === "lane") targetSelectedNodes.add(`lane:${selection.id}`);
      else if (selection.kind === "records") {
        for (const r of selection.records) {
          if (r.kind === "node") targetSelectedNodes.add(r.id);
        }
      }
    }

    setNodes((nds) => {
      let changed = false;
      const nextNds = nds.map((n) => {
        const isSelected = targetSelectedNodes.has(n.id);
        if (n.selected !== isSelected) {
          changed = true;
          return { ...n, selected: isSelected };
        }
        return n;
      });
      return changed ? nextNds : nds;
    });
  }, [selection, setNodes]);

  // Pan/zoom to the active lane when it changes (or is re-selected — the
  // caller bumps `ts` for that). Guard the very first render so we don't
  // fight the initial `fitView` on mount, and dedup by `ts` so unrelated
  // node updates (drags, polling) don't replay the animation.
  const sawFirstFocusRef = useRef(false);
  const lastFocusTsRef = useRef<number | null>(null);
  useEffect(() => {
    if (!focusLane) return;
    if (!sawFirstFocusRef.current) {
      sawFirstFocusRef.current = true;
      lastFocusTsRef.current = focusLane.ts;
      return;
    }
    if (lastFocusTsRef.current === focusLane.ts) return;

    const group = laneGroups(doc).find((g) => g.lane_id === focusLane.laneId);
    if (!group) {
      lastFocusTsRef.current = focusLane.ts;
      return;
    }

    const memberIds = collapsedLaneIds.has(focusLane.laneId)
      ? [`lane:${focusLane.laneId}`]
      : group.node_ids.filter((id) => {
          const n = doc.nodes.find((candidate) => candidate.node_id === id);
          return !n || showCuts || !n.inactive;
        });

    const targetIds = memberIds.length > 0 ? memberIds : [`lane:${focusLane.laneId}`];
    const existingIds = new Set(nodes.map((n) => n.id));
    const fitTargets = targetIds.filter((id) => existingIds.has(id));
    // Nodes may not have rendered yet for a just-switched-to lane; leave
    // lastFocusTsRef unset so a later `nodes` update (this effect also
    // depends on `nodes`) retries the same focus request instead of silently
    // dropping it.
    if (fitTargets.length === 0) return;
    lastFocusTsRef.current = focusLane.ts;

    void reactFlow.fitView({
      nodes: fitTargets.map((id) => ({ id })),
      duration: 450,
      padding: 0.25,
      maxZoom: 1.1,
    });
  }, [focusLane, collapsedLaneIds, doc, nodes, reactFlow, showCuts]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "a") {
        const target = e.target as HTMLElement;
        if (target.tagName !== "INPUT" && target.tagName !== "TEXTAREA") {
          e.stopPropagation();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown, { capture: true });
    return () => window.removeEventListener("keydown", handleKeyDown, { capture: true });
  }, []);

  const inputsFor = (source: string | null): string[] => {
    if (!source) return [];
    const sel = selectedNodeIds.current;
    return sel.length > 1 && sel.includes(source) ? sel : [source];
  };

  const onSelectionChange = useCallback(
    ({ nodes: ns, edges: es }: OnSelectionChangeParams) => {
      if (ignoreNextEmptySelection.current && ns.length === 0 && es.length === 0) {
        ignoreNextEmptySelection.current = false;
        return;
      }

      const uniqueNodeIds = new Set(
        ns.filter((n) => !n.id.startsWith("lane:") && n.type !== "laneGroup").map((n) => n.id)
      );
      selectedNodeIds.current = [...uniqueNodeIds];
      const uniqueStepIds = new Set(
        es.map((e) => (e.data as { stepId?: string })?.stepId).filter(Boolean) as string[]
      );
      const laneIds = new Set(
        ns.filter((n) => n.id.startsWith("lane:")).map((n) => n.id.slice("lane:".length))
      );

      const totalItems = uniqueNodeIds.size + uniqueStepIds.size + laneIds.size;

      if (totalItems === 0) {
        onSelect(null);
      } else if (totalItems === 1) {
        if (uniqueNodeIds.size === 1) {
          onSelect({ kind: "node", id: [...uniqueNodeIds][0] });
        } else if (uniqueStepIds.size === 1) {
          onSelect({ kind: "step", id: [...uniqueStepIds][0] });
        } else if (laneIds.size === 1) {
          onSelect({ kind: "lane", id: [...laneIds][0] });
        }
      } else {
        const records: { kind: "node" | "step"; id: string }[] = [
          ...[...uniqueNodeIds].map((id) => ({ kind: "node" as const, id })),
          ...[...uniqueStepIds].map((id) => ({ kind: "step" as const, id })),
        ];

        if (records.length > 0) {
          onSelect({ kind: "records", records });
        } else {
          onSelect(null);
        }
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
    <div ref={wrapperRef} className="graph-flow-wrapper">
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
        onEdgeClick={(event, edge) => {
          event.stopPropagation();
          ignoreNextEmptySelection.current = true;
          selectedNodeIds.current = [];
          const stepId = (edge.data as { stepId?: string })?.stepId;
          if (stepId) onSelect({ kind: "step", id: stepId });
        }}
        onPaneClick={() => {
          ignoreNextEmptySelection.current = false;
          selectedNodeIds.current = [];
          onSelect(null);
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
        minZoom={0.05}
        fitViewOptions={{ minZoom: 0.05, maxZoom: 1.2, padding: 0.1 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color={document.documentElement.getAttribute("data-theme") === "dark" ? "#334155" : undefined} />
        <Controls />
        <ZoomDeclutter containerRef={wrapperRef} />
      </ReactFlow>
    </div>
  );
}

export function Graph(props: Props) {
  return (
    <ReactFlowProvider>
      <GraphCanvas {...props} />
    </ReactFlowProvider>
  );
}
