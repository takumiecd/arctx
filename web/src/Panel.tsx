// Detail + action panel for the current selection. Shows payloads, and (in
// live mode) lets you add a step (from a node), attach a payload (to a node or
// step), or cut the selected record.

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

import type { RunClient } from "./api";
import type { RunDocument, RunPayload } from "./types";
import type { Selection } from "./Graph";
import {
  laneColors,
  laneLabel,
  nodeLabel,
  payloadsForNode,
  payloadsForStep,
  provenanceFor,
  stepType,
} from "./model";
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

interface AttachTarget {
  key: string;
  label: string;
  selection: Exclude<Selection, null>;
}

interface DetailUnit {
  stepId: string | null;
  outputNodeId: string;
  selected: Exclude<Selection, null>;
}

export function Panel({ doc, selection, client, onSelect }: Props) {
  const qc = useQueryClient();
  const [panelWidth, startPanelResize] = useResizablePanelWidth();
  const [stepType, setStepType] = useState("experiment");
  const [stepContent, setStepContent] = useState("{}");
  const [attachType, setAttachType] = useState("note");
  const [attachContent, setAttachContent] = useState('{"text": ""}');
  const [attachTargetKey, setAttachTargetKey] = useState("step");
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
    mutationFn: (target: AttachTarget) =>
      client.attach({
        target_id: target.selection.id,
        target_kind: target.selection.kind,
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

  useEffect(() => {
    setAttachTargetKey("step");
  }, [selection?.kind, selection?.id]);

  if (!selection) {
    return (
      <aside className="panel" style={{ width: panelWidth }}>
        <PanelResizeHandle onPointerDown={startPanelResize} />
        <p className="muted">Select a node or step.</p>
      </aside>
    );
  }

  const unit = detailUnitFor(doc, selection);
  const stepPayloads = unit.stepId ? payloadsForStep(doc, unit.stepId) : [];
  const nodePayloads = payloadsForNode(doc, unit.outputNodeId);
  const attachTargets = attachTargetsFor(unit);
  const attachTarget = attachTargets.find((target) => target.key === attachTargetKey) ?? attachTargets[0];

  return (
    <aside className="panel" style={{ width: panelWidth }}>
      <PanelResizeHandle onPointerDown={startPanelResize} />
      <h2>
        {unit.stepId ? "step + output" : "node"}{" "}
        <code>{(unit.stepId ?? unit.outputNodeId).slice(0, 12)}</code>
      </h2>

      <section className="panel-view">
        <ProvenanceCard doc={doc} unit={unit} />
        <SelectionContext doc={doc} unit={unit} onSelect={onSelect} />

        {unit.stepId ? (
          <>
            <h3>step payloads ({stepPayloads.length})</h3>
            {stepPayloads.length === 0 && <p className="muted">none</p>}
            {stepPayloads.map((p) => (
              <PayloadCard key={p.payload_id} doc={doc} payload={p} display={payloadDisplayFor(p, doc)} />
            ))}

            <h3>output node notes ({nodePayloads.length})</h3>
            {nodePayloads.length === 0 && <p className="muted">none</p>}
            {nodePayloads.map((p) => (
              <PayloadCard key={p.payload_id} doc={doc} payload={p} display={payloadDisplayFor(p, doc)} />
            ))}
          </>
        ) : (
          <>
            <h3>node payloads ({nodePayloads.length})</h3>
            {nodePayloads.length === 0 && <p className="muted">none</p>}
            {nodePayloads.map((p) => (
              <PayloadCard key={p.payload_id} doc={doc} payload={p} display={payloadDisplayFor(p, doc)} />
            ))}
          </>
        )}
      </section>

      {!client.writable && <p className="muted">read-only (share mode)</p>}

      {client.writable && (
        <details className="actions panel-edit">
          <summary>edit this unit</summary>
          {error && <p className="error">{error}</p>}

          {unit.outputNodeId && (
            <>
              <h3>add next step from output node</h3>
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
              <button disabled={addStep.isPending} onClick={() => addStep.mutate(unit.outputNodeId)}>
                add step
              </button>
            </>
          )}

          <h3>attach payload</h3>
          <label>
            target
            <select value={attachTarget.key} onChange={(e) => setAttachTargetKey(e.target.value)}>
              {attachTargets.map((target) => (
                <option key={target.key} value={target.key}>
                  {target.label}
                </option>
              ))}
            </select>
          </label>
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
          <button disabled={attach.isPending} onClick={() => attach.mutate(attachTarget)}>
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
        </details>
      )}
    </aside>
  );
}

function ProvenanceCard({ doc, unit }: { doc: RunDocument; unit: DetailUnit }) {
  const primaryId = unit.stepId ?? unit.outputNodeId;
  const primaryKind = unit.stepId ? "step" : "node";
  const provenance =
    provenanceFor(doc, primaryId) ??
    (unit.outputNodeId ? provenanceFor(doc, unit.outputNodeId) : null);

  if (!provenance) {
    return (
      <section className="provenance-card missing">
        <h3>provenance</h3>
        <div className="provenance-row">
          <span>lane</span>
          <strong>none recorded</strong>
        </div>
        <p className="muted">
          This record has no lane provenance. It may have been created before lane
          attribution was recorded, or without a work session.
        </p>
      </section>
    );
  }

  const lane = provenance.lane_name || laneLabel(doc, provenance.lane_id);
  return (
    <section className="provenance-card" style={laneVars(doc, provenance.lane_id)}>
      <h3>provenance</h3>
      <div className="provenance-row">
        <span>lane</span>
        <strong className="lane-pill">{lane}</strong>
      </div>
      <div className="provenance-row">
        <span>record</span>
        <code>{primaryKind}:{primaryId.slice(0, 12)}</code>
      </div>
      <div className="provenance-row">
        <span>created by</span>
        <strong>{provenance.user_id}</strong>
      </div>
      <div className="provenance-row">
        <span>event</span>
        <code>{provenance.event_type}</code>
      </div>
      {provenance.created_at && (
        <div className="provenance-row">
          <span>created at</span>
          <time>{provenance.created_at}</time>
        </div>
      )}
    </section>
  );
}

function laneVars(doc: RunDocument, laneId: string): CSSProperties {
  const colors = laneColors(doc, laneId);
  return {
    "--lane-color": colors.laneColor,
    "--lane-bg": colors.laneBg,
  } as CSSProperties;
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

function useResizablePanelWidth(): [
  number,
  (event: ReactPointerEvent<HTMLDivElement>) => void,
] {
  const [width, setWidth] = useState(() => {
    const raw = window.localStorage.getItem("arctx.panelWidth");
    const saved = raw ? Number(raw) : NaN;
    return Number.isFinite(saved) ? clampPanelWidth(saved) : 420;
  });

  useEffect(() => {
    window.localStorage.setItem("arctx.panelWidth", String(width));
  }, [width]);

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    document.body.classList.add("resizing-panel");

    const onMove = (moveEvent: PointerEvent) => {
      setWidth(clampPanelWidth(startWidth + startX - moveEvent.clientX));
    };
    const onUp = () => {
      document.body.classList.remove("resizing-panel");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  };

  return [width, startResize];
}

function clampPanelWidth(width: number): number {
  const max = Math.max(360, window.innerWidth - 280);
  return Math.min(Math.max(width, 300), Math.min(900, max));
}

function PanelResizeHandle({
  onPointerDown,
}: {
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      className="panel-resize-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize detail panel"
      onPointerDown={onPointerDown}
    />
  );
}

function detailUnitFor(doc: RunDocument, selection: Exclude<Selection, null>): DetailUnit {
  if (selection.kind === "step") {
    const step = doc.steps.find((entry) => entry.step_id === selection.id);
    return {
      stepId: step?.step_id ?? selection.id,
      outputNodeId: step?.output_node_id ?? "",
      selected: selection,
    };
  }
  const producer = doc.steps.find((step) => step.output_node_id === selection.id);
  return {
    stepId: producer?.step_id ?? null,
    outputNodeId: selection.id,
    selected: selection,
  };
}

function attachTargetsFor(unit: DetailUnit): AttachTarget[] {
  if (!unit.stepId) {
    return [
      {
        key: "node",
        label: `node (${unit.outputNodeId.slice(0, 8)})`,
        selection: { kind: "node", id: unit.outputNodeId },
      },
    ];
  }
  const targets: AttachTarget[] = [
    {
      key: "step",
      label: `step (${unit.stepId.slice(0, 8)})`,
      selection: { kind: "step", id: unit.stepId },
    },
  ];
  if (unit.outputNodeId) {
    targets.push({
      key: "output-node",
      label: `output node note (${unit.outputNodeId.slice(0, 8)})`,
      selection: { kind: "node", id: unit.outputNodeId },
    });
  }
  return targets;
}

function SelectionContext({
  doc,
  unit,
  onSelect,
}: {
  doc: RunDocument;
  unit: DetailUnit;
  onSelect: (sel: Selection) => void;
}) {
  const nextSteps = doc.steps.filter((step) => step.input_node_ids.includes(unit.outputNodeId));
  if (unit.stepId) {
    const step = doc.steps.find((entry) => entry.step_id === unit.stepId);
    if (!step) return <p className="muted">step not found</p>;
    return (
      <section className="record-context">
        <h3>unit flow</h3>
        <div className="unit-flow">
          <div className="flow-group">
            <div className="flow-heading">
              <span className="flow-label">inputs</span>
              <span className="flow-count">{step.input_node_ids.length}</span>
            </div>
            <div className="flow-list">
              {step.input_node_ids.map((nodeId) => (
                <UnitCard
                  key={nodeId}
                  doc={doc}
                  nodeId={nodeId}
                  onSelect={onSelect}
                />
              ))}
            </div>
          </div>
          <div className="flow-group">
            <div className="flow-heading">
              <span className="flow-label">next</span>
              <span className="flow-count">{nextSteps.length}</span>
            </div>
            <div className="flow-list">
              {nextSteps.length === 0 ? (
                <p className="flow-empty">no next units</p>
              ) : (
                nextSteps.map((nextStep) => (
                  <UnitCard
                    key={nextStep.step_id}
                    doc={doc}
                    nodeId={nextStep.output_node_id}
                    stepId={nextStep.step_id}
                    onSelect={onSelect}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="record-context">
      <h3>unit flow</h3>
      <div className="unit-flow">
        <div className="flow-group">
          <div className="flow-heading">
            <span className="flow-label">next</span>
            <span className="flow-count">{nextSteps.length}</span>
          </div>
          <div className="flow-list">
            {nextSteps.length === 0 ? (
              <p className="flow-empty">no next units</p>
            ) : (
              nextSteps.map((step) => (
                <UnitCard
                  key={step.step_id}
                  doc={doc}
                  nodeId={step.output_node_id}
                  stepId={step.step_id}
                  onSelect={onSelect}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function UnitCard({
  doc,
  nodeId,
  stepId,
  onSelect,
}: {
  doc: RunDocument;
  nodeId: string;
  stepId?: string | null;
  onSelect: (sel: Selection) => void;
}) {
  const producer = stepId
    ? doc.steps.find((step) => step.step_id === stepId)
    : doc.steps.find((step) => step.output_node_id === nodeId);
  const unitStepId = producer?.step_id ?? null;
  const stepPayloads = unitStepId ? payloadsForStep(doc, unitStepId) : [];
  const nodePayloads = payloadsForNode(doc, nodeId);
  const stepSummary = firstPayloadSummary(doc, stepPayloads);
  const nodeSummary = firstPayloadSummary(doc, nodePayloads);
  const title = unitStepId ? stepType(doc, unitStepId) : nodeLabel(doc, nodeId);
  const target: Exclude<Selection, null> = unitStepId
    ? { kind: "step", id: unitStepId }
    : { kind: "node", id: nodeId };
  return (
    <button
      className="unit-card"
      type="button"
      title={unitStepId ? `step ${unitStepId} -> node ${nodeId}` : `node ${nodeId}`}
      onClick={() => onSelect(target)}
    >
      <span className="unit-card-title">{title}</span>
      <span className="unit-card-ids">
        {unitStepId && <code>s:{unitStepId.slice(0, 8)}</code>}
        <code>n:{nodeId.slice(0, 8)}</code>
      </span>
      {stepSummary && <span className="unit-card-summary">{stepSummary}</span>}
      {nodeSummary && (
        <span className="unit-card-summary node-note">
          node: {nodeSummary}
        </span>
      )}
    </button>
  );
}

function firstPayloadSummary(doc: RunDocument, payloads: RunPayload[]): string | null {
  for (const payload of payloads) {
    if (payload.payload_type === "cut") continue;
    const display = payloadDisplayFor(payload, doc);
    const summary = display.summary || display.graphLabel || display.title;
    if (summary && summary.trim()) {
      const normalized = summary.replace(/\s+/g, " ").trim();
      return normalized.length > 86 ? `${normalized.slice(0, 85)}...` : normalized;
    }
  }
  return null;
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
  if (section.kind === "markdown") {
    return <MarkdownView value={section.value} />;
  }
  if (section.kind === "text" || section.kind === "diff") {
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

function MarkdownView({ value }: { value: unknown }) {
  return (
    <div className="payload-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {formatValue(value)}
      </ReactMarkdown>
    </div>
  );
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
