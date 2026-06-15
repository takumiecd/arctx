import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pickClient } from "./api";
import { Graph, type Selection } from "./Graph";
import { Panel } from "./Panel";

const client = pickClient();

export function App() {
  const [selection, setSelection] = useState<Selection>(null);
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["run"],
    queryFn: () => client.getRun(),
    refetchInterval: client.writable ? 5000 : false,
  });

  // Standalone node creation isn't tied to a selection, so it lives in the
  // header rather than the per-selection panel.
  const addNode = useMutation({
    mutationFn: () => client.addNode({}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["run"] }),
  });

  if (isLoading) return <div className="center">loading run…</div>;
  if (error) return <div className="center error">{(error as Error).message}</div>;
  if (!data) return <div className="center">no run</div>;

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
          <button
            className="add-node"
            disabled={addNode.isPending}
            onClick={() => addNode.mutate()}
          >
            + node
          </button>
        )}
        {addNode.isError && (
          <span className="error"> {(addNode.error as Error).message}</span>
        )}
      </header>
      <main>
        <div className="canvas">
          <Graph doc={data} selection={selection} onSelect={setSelection} />
        </div>
        <Panel doc={data} selection={selection} client={client} onSelect={setSelection} />
      </main>
    </div>
  );
}
