import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pickClient } from "./api";
import { Graph, type Selection } from "./Graph";
import { Panel } from "./Panel";

const client = pickClient();

export function App() {
  const [selection, setSelection] = useState<Selection>(null);
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["run"] });
  const { data, isLoading, error } = useQuery({
    queryKey: ["run"],
    queryFn: () => client.getRun(),
    refetchInterval: client.writable ? 5000 : false,
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
    onSuccess: invalidate,
  });

  if (isLoading) return <div className="center">loading run…</div>;
  if (error) return <div className="center error">{(error as Error).message}</div>;
  if (!data) return <div className="center">no run</div>;

  const actionError = (addNode.error ?? createStep.error) as Error | null;

  return (
    <div className="layout">
      <header>
        <strong>arctx</strong> <code>{data.run_id}</code>
        <span className="muted">
          {" "}
          · {data.counts.nodes} nodes · {data.counts.steps} steps
          {!client.writable && " · read-only"}
        </span>
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
            onSelect={setSelection}
            onCreateStep={(inputs, output) => createStep.mutate({ inputs, output })}
            writable={client.writable}
          />
        </div>
        <Panel doc={data} selection={selection} client={client} onSelect={setSelection} />
      </main>
    </div>
  );
}
