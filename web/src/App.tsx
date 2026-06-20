import { useState, type CSSProperties } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pickClient } from "./api";
import { Graph, type Selection } from "./Graph";
import { Panel } from "./Panel";
import { laneColors, laneGroups } from "./model";
import type { RunDocument } from "./types";

const client = pickClient();

export function App() {
  const [selection, setSelection] = useState<Selection>(null);
  const [collapsedLaneIds, setCollapsedLaneIds] = useState<Set<string>>(() => new Set());
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["run"] });
  const { data, isLoading, error } = useQuery({
    queryKey: ["run"],
    queryFn: () => client.getRun(),
    refetchInterval: client.writable ? 5000 : false,
  });
  const { data: savedLayout } = useQuery({
    queryKey: ["web-layout"],
    queryFn: () => client.getLayout(),
    enabled: Boolean(data),
  });

  // Standalone node creation isn't tied to a selection, so it lives in the
  // header rather than the per-selection panel.
  const addNode = useMutation({
    mutationFn: () => client.addNode({}),
    onSuccess: invalidate,
  });

  // Step creation by dragging on the canvas. Output node omitted -> new node;
  // present -> connect into that existing node.
  const createStep = useMutation({
    mutationFn: ({ inputs, output }: { inputs: string[]; output?: string }) =>
      client.addStep({ input_node_ids: inputs, output_node_id: output, type: "step" }),
  });
  const saveLayout = useMutation({
    mutationFn: (nodes: Record<string, { x: number; y: number }>) =>
      client.saveLayout({ view: "default", nodes }),
  });

  if (isLoading) return <div className="center">loading run…</div>;
  if (error) return <div className="center error">{(error as Error).message}</div>;
  if (!data) return <div className="center">no run</div>;

  const actionError = (addNode.error ?? createStep.error) as Error | null;
  const lanes = laneGroups(data);
  const knownLaneIds = new Set(lanes.map((lane) => lane.lane_id).filter(Boolean) as string[]);
  const visibleCollapsedLaneIds = new Set(
    [...collapsedLaneIds].filter((laneId) => knownLaneIds.has(laneId)),
  );
  const toggleLane = (laneId: string) => {
    setCollapsedLaneIds((prev) => {
      const next = new Set(prev);
      if (next.has(laneId)) {
        next.delete(laneId);
      } else {
        next.add(laneId);
        setSelection(null);
      }
      return next;
    });
  };

  return (
    <div className="layout">
      <header>
        <strong>arctx</strong> <code>{data.run_id}</code>
        <span className="muted">
          {" "}
          · {data.counts.nodes} nodes · {data.counts.steps} steps
          {!client.writable && " · read-only"}
        </span>
        {lanes.length > 0 && (
          <span className="lane-toolbar" aria-label="lanes">
            {lanes.map((lane) => {
              const laneId = lane.lane_id;
              if (!laneId) return null;
              const collapsed = visibleCollapsedLaneIds.has(laneId);
              return (
                <button
                  key={lane.group_id}
                  className={`lane-chip${collapsed ? " collapsed" : ""}`}
                  type="button"
                  title={collapsed ? "expand lane" : "collapse lane"}
                  style={laneChipStyle(data, laneId)}
                  onClick={() => toggleLane(laneId)}
                >
                  {collapsed ? "▸" : "▾"} {lane.label}
                </button>
              );
            })}
          </span>
        )}
        {lanes.length === 0 && data.counts.nodes > 1 && (
          <span className="lane-empty">no lane metadata</span>
        )}
        {client.writable && (
          <button className="add-node" disabled={addNode.isPending} onClick={() => addNode.mutate()}>
            + node
          </button>
        )}
        {client.writable && (
          <span className="muted hint"> · drag from a node to make a step</span>
        )}
        {actionError && <span className="error"> {actionError.message}</span>}
      </header>
      <main>
        <div className="canvas">
          <Graph
            doc={data}
            savedNodePositions={savedLayout?.nodes ?? {}}
            onSelect={setSelection}
            onNodePositionsChanged={(positions) => {
              if (client.writable) saveLayout.mutate(positions);
            }}
            onCreateStep={async (inputs, output) => {
              const res = await createStep.mutateAsync({ inputs, output });
              return { outputNodeId: res.step.output_node_id };
            }}
            onRunChanged={invalidate}
            collapsedLaneIds={visibleCollapsedLaneIds}
            onToggleLane={toggleLane}
            writable={client.writable}
          />
        </div>
        <Panel doc={data} selection={selection} client={client} onSelect={setSelection} />
      </main>
    </div>
  );
}

function laneChipStyle(doc: RunDocument, laneId: string): CSSProperties {
  const colors = laneColors(doc, laneId);
  return {
    "--lane-color": colors.laneColor,
    "--lane-bg": colors.laneBg,
  } as CSSProperties;
}
