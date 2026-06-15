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

import { useCallback, useEffect, useRef } from "react";
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
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { layout, type Pos } from "./layout";
import { stepType } from "./model";
import type { RunDocument } from "./types";

export type Selection =
  | { kind: "node"; id: string }
  | { kind: "step"; id: string }
  | null;

// Custom node with source/target handles on each side. ConnectionMode.Loose
// keeps dragging ergonomic while fixed handle IDs let rendered edges enter the
// side that matches graph direction.
function DagNode({ data }: NodeProps) {
  const d = data as { label: string; isRoot: boolean; inactive: boolean };
  const sides = [
    ["top", Position.Top],
    ["right", Position.Right],
    ["bottom", Position.Bottom],
    ["left", Position.Left],
  ] as const;
  return (
    <div className={`dag-node${d.isRoot ? " root" : ""}${d.inactive ? " inactive" : ""}`}>
      {sides.map(([id, p]) => (
        <Handle key={`source-${id}`} type="source" position={p} id={id} />
      ))}
      {sides.map(([id, p]) => (
        <Handle key={`target-${id}`} type="target" position={p} id={id} />
      ))}
      <span>{d.label}</span>
    </div>
  );
}

const nodeTypes = { dag: DagNode };
const NODE_WIDTH = 76;
const NODE_HEIGHT = 34;

interface Props {
  doc: RunDocument;
  onSelect: (sel: Selection) => void;
  onCreateStep: (
    inputNodeIds: string[],
    outputNodeId?: string,
  ) => Promise<{ outputNodeId: string } | void>;
  onRunChanged: () => void;
  writable: boolean;
}

type Side = "top" | "right" | "bottom" | "left";

function edgeSides(source: Pos | undefined, target: Pos | undefined): [Side, Side] {
  if (!source || !target) return ["right", "left"];

  const dx = target.x - source.x;
  const dy = target.y - source.y;

  // Forward edges should usually leave toward the reading direction, but the
  // receiving side should be whichever side makes the route shortest. A child
  // that is down-and-right from its parent reads better as right -> top than as
  // right -> left with an unnecessary wrap around the node.
  if (Math.abs(dx) > 40) {
    const sourceSide = dx > 0 ? "right" : "left";
    if (Math.abs(dy) > 50) {
      return [sourceSide, dy > 0 ? "top" : "bottom"];
    }
    return [sourceSide, dx > 0 ? "left" : "right"];
  }

  return dy >= 0 ? ["bottom", "top"] : ["top", "bottom"];
}

function buildEdges(doc: RunDocument, positions: Record<string, Pos>): Edge[] {
  const out: Edge[] = [];
  for (const s of doc.steps) {
    const edgeColor = s.inactive ? "#94a3b8" : "#475569";
    for (const input of s.input_node_ids) {
      const [sourceHandle, targetHandle] = edgeSides(positions[input], positions[s.output_node_id]);
      out.push({
        id: `${s.step_id}:${input}`,
        source: input,
        target: s.output_node_id,
        sourceHandle,
        targetHandle,
        type: "smoothstep",
        label: stepType(doc, s.step_id),
        data: { stepId: s.step_id },
        labelStyle: { fontSize: 11 },
        labelBgPadding: [6, 3],
        labelBgBorderRadius: 4,
        style: {
          opacity: s.inactive ? 0.35 : 1,
          stroke: edgeColor,
          strokeWidth: 1.8,
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

function eventClientPosition(event: MouseEvent | TouchEvent): Pos | null {
  if ("clientX" in event) {
    return { x: event.clientX, y: event.clientY };
  }
  const touch = event.changedTouches[0] ?? event.touches[0];
  return touch ? { x: touch.clientX, y: touch.clientY } : null;
}

function GraphCanvas({ doc, onSelect, onCreateStep, onRunChanged, writable }: Props) {
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
      return doc.nodes.map((n) => {
        const pendingPos = pendingNodePositions.current.get(n.node_id);
        if (pendingPos) {
          pendingNodePositions.current.delete(n.node_id);
        }
        return {
          id: n.node_id,
          type: "dag",
          position: pendingPos ?? prevPos.get(n.node_id) ?? pos[n.node_id] ?? { x: 0, y: 0 },
          selected: prevSel.get(n.node_id) ?? false,
          data: {
            label: n.node_id === doc.root_node_id ? "root" : n.node_id.slice(0, 8),
            isRoot: n.node_id === doc.root_node_id,
            inactive: n.inactive,
          },
        };
      });
    });
  }, [doc, setNodes]);

  // Edge paths should follow where nodes actually are, including after a user
  // drags nodes around. Use the nearest side instead of letting React Flow
  // default every target toward the top.
  useEffect(() => {
    const fallbackPos = layout(doc);
    const positions: Record<string, Pos> = { ...fallbackPos };
    for (const n of nodes) {
      positions[n.id] = n.position;
    }
    setEdges(buildEdges(doc, positions));
  }, [doc, nodes, setEdges]);

  const inputsFor = (source: string | null): string[] => {
    if (!source) return [];
    const sel = selectedNodeIds.current;
    return sel.length > 1 && sel.includes(source) ? sel : [source];
  };

  const onSelectionChange = useCallback(
    ({ nodes: ns, edges: es }: OnSelectionChangeParams) => {
      selectedNodeIds.current = ns.map((n) => n.id);
      if (ns.length === 1 && es.length === 0) {
        onSelect({ kind: "node", id: ns[0].id });
      } else if (es.length === 1 && ns.length === 0) {
        onSelect({ kind: "step", id: (es[0].data as { stepId: string }).stepId });
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
      onSelectionChange={onSelectionChange}
      onConnect={writable ? onConnect : undefined}
      onConnectStart={writable ? onConnectStart : undefined}
      onConnectEnd={writable ? onConnectEnd : undefined}
      nodesConnectable={writable}
      connectionMode={ConnectionMode.Loose}
      fitView
      proOptions={{ hideAttribution: true }}
    >
      <Background />
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
