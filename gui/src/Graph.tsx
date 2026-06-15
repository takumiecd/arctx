// React Flow view of a run. Nodes = arctx Nodes; edges = arctx Steps
// (one edge per input -> output, labeled with the step's payload type).
// Cut/inactive records are dimmed. Clicking a node or an edge selects it.

import { useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { layout } from "./layout";
import type { RunDocument } from "./types";
import { stepType } from "./model";

export type Selection =
  | { kind: "node"; id: string }
  | { kind: "step"; id: string }
  | null;

interface Props {
  doc: RunDocument;
  selection: Selection;
  onSelect: (sel: Selection) => void;
}

export function Graph({ doc, selection, onSelect }: Props) {
  const positions = useMemo(() => layout(doc), [doc]);

  const nodes: Node[] = useMemo(
    () =>
      doc.nodes.map((n) => {
        const isRoot = n.node_id === doc.root_node_id;
        const selected = selection?.kind === "node" && selection.id === n.node_id;
        return {
          id: n.node_id,
          position: positions[n.node_id] ?? { x: 0, y: 0 },
          data: { label: isRoot ? "root" : n.node_id.slice(0, 8) },
          style: {
            opacity: n.inactive ? 0.4 : 1,
            border: selected ? "2px solid #2563eb" : "1px solid #94a3b8",
            borderRadius: 8,
            padding: 6,
            fontSize: 12,
            background: isRoot ? "#ecfdf5" : "#fff",
          },
        };
      }),
    [doc, positions, selection],
  );

  const edges: Edge[] = useMemo(() => {
    const out: Edge[] = [];
    for (const s of doc.steps) {
      const selected = selection?.kind === "step" && selection.id === s.step_id;
      for (const input of s.input_node_ids) {
        out.push({
          id: `${s.step_id}:${input}`,
          source: input,
          target: s.output_node_id,
          label: stepType(doc, s.step_id),
          animated: false,
          data: { stepId: s.step_id },
          labelStyle: { fontSize: 11 },
          style: {
            opacity: s.inactive ? 0.35 : 1,
            stroke: selected ? "#2563eb" : "#64748b",
            strokeWidth: selected ? 2.5 : 1.5,
          },
        });
      }
    }
    return out;
  }, [doc, selection]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      fitView
      onNodeClick={(_, n) => onSelect({ kind: "node", id: n.id })}
      onEdgeClick={(_, e) =>
        onSelect({ kind: "step", id: (e.data as { stepId: string }).stepId })
      }
      onPaneClick={() => onSelect(null)}
      proOptions={{ hideAttribution: true }}
    >
      <Background />
      <Controls />
    </ReactFlow>
  );
}
