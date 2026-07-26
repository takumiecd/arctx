// Renders one payload as a card: title/summary/fields from the registered
// display renderer, optional media/sections/custom element, and a raw-JSON
// fallback.

import { useEffect, useRef } from "react";

import type { RunDocument, RunPayload } from "../types";
import { payloadElementFor, type PayloadDisplay, type PayloadSection } from "../payloadExtensions";
import { formatValue, tableData } from "./format";
import { MarkdownView, PayloadMediaView, SanitizedHtmlView } from "./markdown";
import type { PayloadMedia } from "../payloadExtensions";

export function PayloadCard({
  doc,
  payload,
  display,
  onCopyToEdit,
}: {
  doc: RunDocument;
  payload: RunPayload;
  display: PayloadDisplay;
  onCopyToEdit?: (text: string) => void;
}) {
  const element = payloadElementFor(payload);
  return (
    <section className={`payload-card${display.raw ? " raw" : ""}`}>
      <div className="payload-card-head">
        <strong>{display.title}</strong>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {onCopyToEdit && (
            <button
              type="button"
              className="payload-copy-btn"
              onClick={() => {
                const text = typeof payload.content?.text === "string" ? payload.content.text : "";
                onCopyToEdit(text);
              }}
            >
              Copy to Edit
            </button>
          )}
          <code>{payload.payload_id.slice(0, 12)}</code>
        </div>
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
  if (section.kind === "html") {
    return <SanitizedHtmlView value={section.value} />;
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
