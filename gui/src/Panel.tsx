// Detail + action panel for the current selection. Shows payloads, and (in
// live mode) lets you add a step, attach a note, or cut the selected record.

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { RunClient } from "./api";
import type { RunDocument } from "./types";
import type { Selection } from "./Graph";
import { payloadsForNode, payloadsForStep } from "./model";

interface Props {
  doc: RunDocument;
  selection: Selection;
  client: RunClient;
  onSelect: (sel: Selection) => void;
}

export function Panel({ doc, selection, client, onSelect }: Props) {
  const qc = useQueryClient();
  const [stepType, setStepType] = useState("experiment");
  const [stepContent, setStepContent] = useState("{}");
  const [noteText, setNoteText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["run"] });

  const addStep = useMutation({
    mutationFn: (nodeId: string) =>
      client.addStep({
        input_node_ids: [nodeId],
        type: stepType,
        content: parseJson(stepContent),
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e: Error) => setError(e.message),
  });

  const attach = useMutation({
    mutationFn: (nodeId: string) =>
      client.attach({ node_id: nodeId, type: "note", content: { text: noteText } }),
    onSuccess: () => {
      setNoteText("");
      setError(null);
      invalidate();
    },
    onError: (e: Error) => setError(e.message),
  });

  const cut = useMutation({
    mutationFn: (sel: Exclude<Selection, null>) =>
      client.cut({ target_id: sel.id, target_kind: sel.kind }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e: Error) => setError(e.message),
  });

  if (!selection) {
    return (
      <aside className="panel">
        <p className="muted">Select a node or step.</p>
      </aside>
    );
  }

  const payloads =
    selection.kind === "node"
      ? payloadsForNode(doc, selection.id)
      : payloadsForStep(doc, selection.id);

  return (
    <aside className="panel">
      <h2>
        {selection.kind} <code>{selection.id.slice(0, 12)}</code>
      </h2>

      <h3>payloads ({payloads.length})</h3>
      {payloads.length === 0 && <p className="muted">none</p>}
      {payloads.map((p) => (
        <pre key={p.payload_id} className="payload">
          {JSON.stringify(p, null, 2)}
        </pre>
      ))}

      {!client.writable && <p className="muted">read-only (share mode)</p>}

      {client.writable && (
        <div className="actions">
          {error && <p className="error">{error}</p>}

          {selection.kind === "node" && (
            <>
              <h3>add step from this node</h3>
              <label>
                type
                <input value={stepType} onChange={(e) => setStepType(e.target.value)} />
              </label>
              <label>
                content (JSON)
                <textarea
                  rows={3}
                  value={stepContent}
                  onChange={(e) => setStepContent(e.target.value)}
                />
              </label>
              <button
                disabled={addStep.isPending}
                onClick={() => addStep.mutate(selection.id)}
              >
                add step
              </button>

              <h3>attach note</h3>
              <textarea
                rows={2}
                value={noteText}
                placeholder="note text"
                onChange={(e) => setNoteText(e.target.value)}
              />
              <button
                disabled={attach.isPending || !noteText}
                onClick={() => attach.mutate(selection.id)}
              >
                attach note
              </button>
            </>
          )}

          <h3>cut</h3>
          <button
            className="danger"
            disabled={cut.isPending}
            onClick={() => {
              cut.mutate(selection);
              onSelect(null);
            }}
          >
            cut this {selection.kind}
          </button>
        </div>
      )}
    </aside>
  );
}

function parseJson(raw: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("content must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}
