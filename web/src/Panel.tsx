// Detail + action panel for the current selection. Shows payloads, and (in
// live mode) lets you add a step (from a node), attach a payload (to a node or
// step), or cut the selected record.

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { RunClient } from "./api";
import type { RunDocument, RunPayload } from "./types";
import type { Selection } from "./Graph";
import { payloadsForNode, payloadsForStep } from "./model";
import {
  payloadDisplayFor,
  payloadElementFor,
  type PayloadDisplay,
  type PayloadMedia,
  type PayloadSection,
} from "./payloadExtensions";

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
        <PayloadCard key={p.payload_id} doc={doc} payload={p} display={payloadDisplayFor(p, doc)} />
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

function PayloadCard({
  doc,
  payload,
  display,
}: {
  doc: RunDocument;
  payload: RunPayload;
  display: PayloadDisplay;
}) {
  const element = payloadElementFor(payload);
  return (
    <section className={`payload-card${display.raw ? " raw" : ""}`}>
      <div className="payload-card-head">
        <strong>{display.title}</strong>
        <code>{payload.payload_id.slice(0, 12)}</code>
      </div>
      {display.summary && <p className="payload-summary">{display.summary}</p>}
      {display.media?.map((media, index) => (
        <PayloadMediaView key={`${media.src}:${index}`} media={media} />
      ))}
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
      {element && (
        <PayloadCustomElement
          tagName={element.tagName}
          doc={doc}
          payload={payload}
          display={display}
        />
      )}
      {display.sections?.map((section, index) => (
        <PayloadSectionView key={`${section.title}:${index}`} section={section} />
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
  const body = (
    <div className="payload-section">
      <h4>{section.title}</h4>
      <PayloadSectionBody section={section} />
    </div>
  );
  if (!section.collapsed) return body;
  return (
    <details className="payload-section-details">
      <summary>{section.title}</summary>
      <PayloadSectionBody section={section} />
    </details>
  );
}

function PayloadSectionBody({ section }: { section: PayloadSection }) {
  if (section.kind === "image") {
    return <PayloadMediaView media={mediaFromSection(section)} />;
  }
  if (section.kind === "text" || section.kind === "markdown" || section.kind === "diff") {
    return (
      <pre className={`payload payload-text${section.kind === "diff" ? " payload-diff" : ""}`}>
        {formatValue(section.value)}
      </pre>
    );
  }
  if (section.kind === "table") {
    return <PayloadTable value={section.value} />;
  }
  return <pre className="payload">{JSON.stringify(section.value, null, 2)}</pre>;
}

function PayloadMediaView({ media }: { media: PayloadMedia }) {
  const src = safeImageSrc(media.src);
  if (!src) {
    return <p className="muted payload-media-blocked">blocked image source</p>;
  }
  return (
    <figure className="payload-media">
      <img src={src} alt={media.alt ?? ""} loading="lazy" />
      {media.caption && <figcaption>{media.caption}</figcaption>}
    </figure>
  );
}

function PayloadTable({ value }: { value: unknown }) {
  const table = tableData(value);
  if (!table) {
    return <pre className="payload">{JSON.stringify(value, null, 2)}</pre>;
  }
  return (
    <div className="payload-table-wrap">
      <table className="payload-table">
        <thead>
          <tr>
            {table.columns.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, index) => (
            <tr key={index}>
              {table.columns.map((col) => (
                <td key={col}>{formatValue(row[col])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PayloadCustomElement({
  tagName,
  doc,
  payload,
  display,
}: {
  tagName: string;
  doc: RunDocument;
  payload: RunPayload;
  display: PayloadDisplay;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    host.replaceChildren();
    const element = document.createElement(tagName) as HTMLElement & {
      doc?: RunDocument;
      payload?: RunPayload;
      display?: PayloadDisplay;
    };
    element.doc = doc;
    element.payload = payload;
    element.display = display;
    host.appendChild(element);
    return () => host.replaceChildren();
  }, [tagName, doc, payload, display]);
  return <div className="payload-custom-element-host" ref={ref} />;
}

function mediaFromSection(section: PayloadSection): PayloadMedia {
  if (typeof section.value === "string") {
    return { kind: "image", src: section.value, alt: section.title };
  }
  if (typeof section.value === "object" && section.value !== null && !Array.isArray(section.value)) {
    const raw = section.value as Record<string, unknown>;
    return {
      kind: "image",
      src: typeof raw.src === "string" ? raw.src : "",
      alt: typeof raw.alt === "string" ? raw.alt : section.title,
      caption: typeof raw.caption === "string" ? raw.caption : undefined,
    };
  }
  return { kind: "image", src: "", alt: section.title };
}

function safeImageSrc(src: string): string | null {
  if (src.length > 7_000_000) return null;
  if (/^data:image\/(png|jpeg|webp);base64,[a-z0-9+/=\s]+$/i.test(src)) {
    return src;
  }
  if (src.startsWith("artifact://")) {
    const path = src.slice("artifact://".length).replace(/^\/+/, "");
    return artifactPath(path);
  }
  if (src.startsWith("/artifacts/")) {
    return artifactPath(src.slice("/artifacts/".length));
  }
  return null;
}

function artifactPath(path: string): string | null {
  const parts = path.split("/").filter(Boolean);
  if (!parts.length || parts.some((part) => part === "." || part === "..")) return null;
  return `/artifacts/${parts.map(encodeURIComponent).join("/")}`;
}

function tableData(value: unknown): { columns: string[]; rows: Record<string, unknown>[] } | null {
  if (Array.isArray(value)) {
    const rows = value
      .filter((row) => typeof row === "object" && row !== null && !Array.isArray(row))
      .map((row) => row as Record<string, unknown>);
    if (!rows.length) return null;
    const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
    return { columns, rows };
  }
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    const raw = value as Record<string, unknown>;
    const rawColumns = Array.isArray(raw.columns) ? raw.columns.map(String) : [];
    const rawRows = Array.isArray(raw.rows) ? raw.rows : [];
    const rows = rawRows.map((row) => {
      if (Array.isArray(row)) {
        return Object.fromEntries(rawColumns.map((col, index) => [col, row[index]]));
      }
      return typeof row === "object" && row !== null ? (row as Record<string, unknown>) : {};
    });
    const columns = rawColumns.length
      ? rawColumns
      : Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
    return columns.length && rows.length ? { columns, rows } : null;
  }
  return null;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
