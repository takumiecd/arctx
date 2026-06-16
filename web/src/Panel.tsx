// Detail + action panel for the current selection. Shows payloads, and (in
// live mode) lets you add a step (from a node), attach a payload (to a node or
// step), or cut the selected record.

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { RunClient } from "./api";
import type { RunDocument, RunPayload } from "./types";
import type { Selection } from "./Graph";
import { payloadsForNode, payloadsForStep } from "./model";
import { payloadDisplayFor, type PayloadDisplay, type PayloadSection } from "./payloadExtensions";

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
  const [attachType, setAttachType] = useState("note");
  const [attachContent, setAttachContent] = useState('{"text": ""}');
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["run"] });
  const fail = (e: Error) => setError(e.message);

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
    onError: fail,
  });

  const attach = useMutation({
    mutationFn: (sel: Exclude<Selection, null>) =>
      client.attach({
        target_id: sel.id,
        target_kind: sel.kind,
        type: attachType,
        content: parseJson(attachContent),
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: fail,
  });

  const cut = useMutation({
    mutationFn: (sel: Exclude<Selection, null>) =>
      client.cut({ target_id: sel.id, target_kind: sel.kind }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: fail,
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
        <PayloadCard key={p.payload_id} payload={p} display={payloadDisplayFor(p, doc)} />
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
              <button disabled={addStep.isPending} onClick={() => addStep.mutate(selection.id)}>
                add step
              </button>
            </>
          )}

          <h3>attach payload to this {selection.kind}</h3>
          <label>
            type
            <input value={attachType} onChange={(e) => setAttachType(e.target.value)} />
          </label>
          <label>
            content (JSON)
            <textarea
              rows={3}
              value={attachContent}
              onChange={(e) => setAttachContent(e.target.value)}
            />
          </label>
          <button disabled={attach.isPending} onClick={() => attach.mutate(selection)}>
            attach payload
          </button>

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

function PayloadCard({ payload, display }: { payload: RunPayload; display: PayloadDisplay }) {
  return (
    <section className={`payload-card${display.raw ? " raw" : ""}`}>
      <div className="payload-card-head">
        <strong>{display.title}</strong>
        <code>{payload.payload_id.slice(0, 12)}</code>
      </div>
      {display.summary && <p className="payload-summary">{display.summary}</p>}
      {display.fields && display.fields.length > 0 && (
        <dl className="payload-fields">
          {display.fields.map((field) => (
            <div key={field.label}>
              <dt>{field.label}</dt>
              <dd>{formatValue(field.value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {display.sections?.map((section) => (
        <PayloadSectionView key={section.title} section={section} />
      ))}
      {!display.raw && (
        <details className="payload-raw">
          <summary>raw JSON</summary>
          <pre className="payload">{JSON.stringify(payload, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}

function PayloadSectionView({ section }: { section: PayloadSection }) {
  return (
    <div className="payload-section">
      <h4>{section.title}</h4>
      {section.kind === "text" ? (
        <pre className="payload payload-text">{formatValue(section.value)}</pre>
      ) : (
        <pre className="payload">{JSON.stringify(section.value, null, 2)}</pre>
      )}
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
