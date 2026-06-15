// Data adapters. The UI only ever talks to a `RunClient`, so the same
// components serve both modes:
//
//   - LiveClient   -> talks to `arctx serve` (read + write)
//   - StaticClient -> renders an embedded run document (read-only, for sharing)
//
// `pickClient()` chooses based on what the page provides.

import type {
  AddStepRequest,
  AttachRequest,
  CutRequest,
  RunDocument,
} from "./types";

export interface RunClient {
  readonly writable: boolean;
  getRun(): Promise<RunDocument>;
  addStep(req: AddStepRequest): Promise<void>;
  attach(req: AttachRequest): Promise<void>;
  cut(req: CutRequest): Promise<void>;
}

class ReadOnlyError extends Error {
  constructor() {
    super("this run is read-only (static share mode)");
  }
}

export class LiveClient implements RunClient {
  readonly writable = true;
  constructor(private readonly base: string = "") {}

  private async req<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(this.base + path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error((data as { error?: string }).error ?? `HTTP ${res.status}`);
    }
    return data as T;
  }

  getRun() {
    return this.req<RunDocument>("/run");
  }
  async addStep(req: AddStepRequest) {
    await this.req("/step", { method: "POST", body: JSON.stringify(req) });
  }
  async attach(req: AttachRequest) {
    await this.req("/attach", { method: "POST", body: JSON.stringify(req) });
  }
  async cut(req: CutRequest) {
    await this.req("/cut", { method: "POST", body: JSON.stringify(req) });
  }
}

export class StaticClient implements RunClient {
  readonly writable = false;
  constructor(private readonly doc: RunDocument) {}
  async getRun() {
    return this.doc;
  }
  async addStep(): Promise<void> {
    throw new ReadOnlyError();
  }
  async attach(): Promise<void> {
    throw new ReadOnlyError();
  }
  async cut(): Promise<void> {
    throw new ReadOnlyError();
  }
}

// Find an embedded run document (static/share mode), if present.
function embeddedDoc(): RunDocument | null {
  const el = document.getElementById("arctx-run");
  if (!el?.textContent) return null;
  try {
    return JSON.parse(el.textContent) as RunDocument;
  } catch {
    return null;
  }
}

export function pickClient(): RunClient {
  const embedded = embeddedDoc();
  if (embedded) return new StaticClient(embedded);
  // Live mode. `?api=` overrides the base; default is same-origin (dev server
  // proxies the API routes to `arctx serve`).
  const api = new URLSearchParams(location.search).get("api") ?? "";
  return new LiveClient(api);
}
