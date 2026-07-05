// Pure value formatting / image-source safety / table-shape helpers shared
// by payload rendering and markdown rendering.

import { artifactSrc } from "../api";

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export function safeImageSrc(src: string): string | null {
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

export function artifactPath(path: string): string | null {
  const parts = path.split("/").filter(Boolean);
  if (!parts.length || parts.some((part) => part === "." || part === "..")) return null;
  // artifactSrc appends ?run= when the picker has switched runs, so the file
  // resolves against the selected run rather than the server's bound run.
  return artifactSrc(`/artifacts/${parts.map(encodeURIComponent).join("/")}`);
}

export function tableData(value: unknown): { columns: string[]; rows: Record<string, unknown>[] } | null {
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
