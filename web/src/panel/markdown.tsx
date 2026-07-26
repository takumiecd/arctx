// Markdown / sanitized-HTML rendering for note and summary payloads.

import { createContext, useContext, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

import type { RunClient } from "../api";
import { type PayloadMedia } from "../payloadExtensions";
import { formatValue, safeImageSrc } from "./format";

// Set of artifact URLs (e.g. "/artifacts/ast_xxx_file.png") that may be
// referenced from the record currently being rendered. `null` means no
// scoping (static/share mode, or still loading) — render everything.
const ArtifactScopeContext = createContext<Set<string> | null>(null);

export function artifactKey(src: string): string {
  let s = src;
  if (s.startsWith("artifact://")) s = `/artifacts/${s.slice("artifact://".length).replace(/^\/+/, "")}`;
  try {
    return decodeURI(s);
  } catch {
    return s;
  }
}

export function isArtifactUrl(src: string): boolean {
  return src.startsWith("/artifacts/") || src.startsWith("artifact://");
}

// Payload cards render without artifact scoping. Assets are being re-modelled
// as (commit, path) git references; scoping will come back with them.
export function ScopedPayloads({
  client: _client,
  recordId: _recordId,
  children,
}: {
  client: RunClient;
  recordId: string;
  children: ReactNode;
}) {
  return <ArtifactScopeContext.Provider value={null}>{children}</ArtifactScopeContext.Provider>;
}

export function MarkdownView({ value }: { value: unknown }) {
  return (
    <div className="payload-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{ img: ScopedMarkdownImg }}
      >
        {formatValue(value)}
      </ReactMarkdown>
    </div>
  );
}

export function SummaryBody({
  text,
  format,
}: {
  text: string;
  format: "markdown" | "html" | "text";
}) {
  if (format === "html") return <SanitizedHtmlView value={text} />;
  if (format === "text") {
    return <pre className="payload payload-text">{text}</pre>;
  }
  return <MarkdownView value={text} />;
}

export function SanitizedHtmlView({ value }: { value: unknown }) {
  return (
    <div
      className="payload-markdown"
      dangerouslySetInnerHTML={{ __html: sanitizeSummaryHtml(formatValue(value)) }}
    />
  );
}

export function summaryFormat(value: unknown): "markdown" | "html" | "text" {
  if (value === "html" || value === "text") return value;
  return "markdown";
}

const SUMMARY_HTML_ALLOWED_TAGS = new Set([
  "a",
  "b",
  "blockquote",
  "br",
  "code",
  "div",
  "em",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "hr",
  "i",
  "li",
  "ol",
  "p",
  "pre",
  "span",
  "strong",
  "table",
  "tbody",
  "td",
  "th",
  "thead",
  "tr",
  "ul",
]);
const SUMMARY_HTML_URI_ATTRS = new Set(["href"]);
const SUMMARY_HTML_TEXT_ATTRS = new Set(["title", "aria-label"]);

function sanitizeSummaryHtml(html: string): string {
  if (typeof window === "undefined") return escapeHtml(html);
  const parser = new DOMParser();
  const doc = parser.parseFromString(`<div>${html}</div>`, "text/html");
  const root = doc.body.firstElementChild;
  if (!root) return "";
  sanitizeHtmlNode(root);
  return root.innerHTML;
}

function sanitizeHtmlNode(node: Node): void {
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === Node.ELEMENT_NODE) {
      const element = child as HTMLElement;
      const tag = element.tagName.toLowerCase();
      if (!SUMMARY_HTML_ALLOWED_TAGS.has(tag)) {
        element.replaceWith(document.createTextNode(element.textContent ?? ""));
        continue;
      }
      for (const attr of Array.from(element.attributes)) {
        const name = attr.name.toLowerCase();
        const value = attr.value;
        if (name.startsWith("on") || name === "style") {
          element.removeAttribute(attr.name);
        } else if (SUMMARY_HTML_URI_ATTRS.has(name)) {
          if (!isSafeSummaryUrl(value)) element.removeAttribute(attr.name);
        } else if (!SUMMARY_HTML_TEXT_ATTRS.has(name)) {
          element.removeAttribute(attr.name);
        }
      }
      if (tag === "a" && element.getAttribute("href")) {
        element.setAttribute("rel", "noreferrer noopener");
      }
    }
    sanitizeHtmlNode(child);
  }
}

function isSafeSummaryUrl(value: string): boolean {
  const trimmed = value.trim();
  return (
    trimmed.startsWith("#") ||
    trimmed.startsWith("/") ||
    /^https?:\/\//i.test(trimmed) ||
    /^mailto:/i.test(trimmed)
  );
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function ScopedMarkdownImg({ src, alt }: { src?: string; alt?: string }) {
  const scope = useContext(ArtifactScopeContext);
  const raw = typeof src === "string" ? src : "";
  if (isArtifactUrl(raw) && scope && !scope.has(artifactKey(raw))) {
    return <span className="muted payload-media-blocked">⚠ asset not in scope</span>;
  }
  const safe = isArtifactUrl(raw) ? safeImageSrc(raw) : raw;
  if (!safe) {
    return <span className="muted payload-media-blocked">blocked image source</span>;
  }
  return <img src={safe} alt={alt ?? ""} loading="lazy" />;
}

export function PayloadMediaView({ media }: { media: PayloadMedia }) {
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
