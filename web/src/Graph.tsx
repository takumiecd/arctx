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
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type FinalConnectionState,
  type Node,
  type NodeProps,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { layout } from "./layout";
import { stepType } from "./model";
import type { RunDocument } from "./types";

export type Selection =
  | { kind: "node"; id: string }
  | { kind: "step"; id: string }
  | null;

// Custom node with a handle on each side. ConnectionMode.Loose lets any handle
// act as both source and target, so you can drag from/onto any side.
function DagNode({ data }: NodeProps) {
  const d = data as { label: string; isRoot: boolean; inactive: boolean };
  const sides = [Position.Top, Position.Right, Position.Bottom, Position.Left];
  return (
    <div className={`dag-node${d.isRoot ? " root" : ""}${d.inactive ? " inactive" : ""}`}>
      {sides.map((p) => (
        <Handle key={p} type="source" position={p} id={p} />
      ))}
      <span>{d.label}</span>
    </div>
  );
}

const nodeTypes = { dag: DagNode };

interface Props {
  doc: RunDocument;
  onSelect: (sel: Selection) => void;
  onCreateStep: (inputNodeIds: string[], outputNodeId?: string) => void;
  writable: boolean;
}

function buildEdges(doc: RunDocument): Edge[] {
  const out: Edge[] = [];
  for (const s of doc.steps) {
    for (const input of s.input_node_ids) {
      out.push({
        id: `${s.step_id}:${input}`,
        source: input,
        target: s.output_node_id,
        label: stepType(doc, s.step_id),
        data: { stepId: s.step_id },
        labelStyle: { fontSize: 11 },
        style: {
          opacity: s.inactive ? 0.35 : 1,
          stroke: "#64748b",
          strokeWidth: 1.5,
        },
      });
    }
  }
  return out;
}

export function Graph({ doc, onSelect, onCreateStep, writable }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // The node the current connection drag started from, and the live multi-node
  // selection (used as step inputs when several nodes are selected).
  const dragSource = useRef<string | null>(null);
  const selectedNodeIds = useRef<string[]>([]);

  // Rebuild from the run document, preserving manual positions and selection
  // across polled refetches so the canvas doesn't jump.
  useEffect(() => {
    const pos = layout(doc);
    setNodes((prev) => {
      const prevPos = new Map(prev.map((n) => [n.id, n.position]));
      const prevSel = new Map(prev.map((n) => [n.id, n.selected]));
      return doc.nodes.map((n) => ({
        id: n.node_id,
        type: "dag",
        position: prevPos.get(n.node_id) ?? pos[n.node_id] ?? { x: 0, y: 0 },
        selected: prevSel.get(n.node_id) ?? false,
        data: {
          label: n.node_id === doc.root_node_id ? "root" : n.node_id.slice(0, 8),
          isRoot: n.node_id === doc.root_node_id,
          inactive: n.inactive,
        },
      }));
    });
    setEdges(buildEdges(doc));
  }, [doc, setNodes, setEdges]);

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
        onCreateStep(inputsFor(c.source), c.target);
      }
    },
    [onCreateStep],
  );

  const onConnectStart = useCallback(
    (_: unknown, params: { nodeId: string | null }) => {
      dragSource.current = params.nodeId;
    },
    [],
  );

  // Dropped on empty canvas (no target node) -> mint a new output node.
  const onConnectEnd = useCallback(
    (_: unknown, state: FinalConnectionState) => {
      if (!state.toNode && dragSource.current) {
        onCreateStep(inputsFor(dragSource.current));
      }
      dragSource.current = null;
    },
    [onCreateStep],
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
