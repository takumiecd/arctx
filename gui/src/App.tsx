import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { pickClient } from "./api";
import { Graph, type Selection } from "./Graph";
import { Panel } from "./Panel";

const client = pickClient();

export function App() {
  const [selection, setSelection] = useState<Selection>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ["run"],
    queryFn: () => client.getRun(),
    refetchInterval: client.writable ? 5000 : false,
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
