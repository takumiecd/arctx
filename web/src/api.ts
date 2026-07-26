// Data adapters. The UI only ever talks to a `RunClient`, so the same
// components serve both modes:
//
//   - LiveClient   -> talks to `arctx serve` (read + write)
//   - StaticClient -> renders an embedded run document (read-only, for sharing)
//
// `pickClient()` chooses based on what the page provides.

import type {
  AddStepRequest,
  AddStepResponse,
  AttachRequest,
  CreateLaneRequest,
  CreateLaneResponse,
  CreateRunRequest,
  CreateRunResponse,
  CutRequest,
  ReparentRequest,
  RunDocument,
  RunSummary,
  RunsResponse,
  UncutRequest,
  WebLayout,
  ExtensionsResponse,
} from "./types";

// The run the live API should target, overriding the server's bound run. Set
// by the run picker. Kept module-level (not just on the client) so artifact
// <img>/link URLs — which can't send request headers — can append `?run=`.
let activeRunId: string | null = null;
export function setActiveRunId(id: string | null): void {
  activeRunId = id;
}
export function getActiveRunId(): string | null {
  return activeRunId;
}

// Append the active run override to an artifact URL so it resolves against the
// run currently selected in the picker rather than the server's bound run.
export function artifactSrc(url: string): string {
  if (!activeRunId) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}run=${encodeURIComponent(activeRunId)}`;
}

export interface RunClient {
  readonly writable: boolean;
  activeLaneId: string | null;
  activeRunId: string | null;
  listRuns(): Promise<RunSummary[]>;
  createRun(req: CreateRunRequest): Promise<CreateRunResponse>;
  getRun(): Promise<RunDocument>;
  getLayout(): Promise<WebLayout>;
  saveLayout(layout: WebLayout): Promise<WebLayout>;
  addStep(req: AddStepRequest): Promise<AddStepResponse>;
  attach(req: AttachRequest): Promise<void>;
  cut(req: CutRequest): Promise<void>;
  uncut(req: UncutRequest): Promise<void>;
  reparent(req: ReparentRequest): Promise<AddStepResponse>;
  createLane(req: CreateLaneRequest): Promise<CreateLaneResponse>;
  getExtensions(): Promise<ExtensionsResponse>;
  enableExtension(name: string): Promise<void>;
  disableExtension(name: string): Promise<void>;
}

class ReadOnlyError extends Error {
  constructor() {
    super("this run is read-only (static share mode)");
  }
}

export class LiveClient implements RunClient {
  readonly writable = true;
  activeLaneId: string | null = null;
  // Mirror onto the module-level state so artifact URLs (no headers) agree.
  get activeRunId(): string | null {
    return getActiveRunId();
  }
  set activeRunId(value: string | null) {
    setActiveRunId(value);
  }
  constructor(private readonly base: string = "") {}

  private async req<T>(path: string, init?: RequestInit): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.activeLaneId) {
      headers["X-Arctx-Work-Session-Id"] = this.activeLaneId;
    }
    if (this.activeRunId) {
      headers["X-Arctx-Run-Id"] = this.activeRunId;
    }
    const res = await fetch(this.base + path, {
      headers,
      ...init,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error((data as { error?: string }).error ?? `HTTP ${res.status}`);
    }
    return data as T;
  }

  async listRuns() {
    const res = await this.req<RunsResponse>("/runs");
    return res.runs;
  }
  createRun(req: CreateRunRequest) {
    return this.req<CreateRunResponse>("/runs", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }
  getRun() {
    return this.req<RunDocument>("/run");
  }
  getLayout() {
    return this.req<WebLayout>("/web/layout").catch(() => ({ view: "default", nodes: {} }));
  }
  async saveLayout(layout: WebLayout) {
    return this.req<WebLayout>("/web/layout", {
      method: "PUT",
      body: JSON.stringify(layout),
    }).catch(() => layout);
  }
  async addStep(req: AddStepRequest) {
    return this.req<AddStepResponse>("/step", { method: "POST", body: JSON.stringify(req) });
  }
  async attach(req: AttachRequest) {
    await this.req("/attach", { method: "POST", body: JSON.stringify(req) });
  }
  async cut(req: CutRequest) {
    await this.req("/cut", { method: "POST", body: JSON.stringify(req) });
  }
  async uncut(req: UncutRequest) {
    await this.req("/uncut", { method: "POST", body: JSON.stringify(req) });
  }
  async reparent(req: ReparentRequest) {
    return this.req<AddStepResponse>("/reparent", { method: "POST", body: JSON.stringify(req) });
  }
  async createLane(req: CreateLaneRequest) {
    return this.req<CreateLaneResponse>("/lane", { method: "POST", body: JSON.stringify(req) });
  }
  getExtensions() {
    return this.req<ExtensionsResponse>("/ext");
  }
  async enableExtension(name: string) {
    await this.req("/ext/enable", { method: "POST", body: JSON.stringify({ name }) });
  }
  async disableExtension(name: string) {
    await this.req("/ext/disable", { method: "POST", body: JSON.stringify({ name }) });
  }
}

export class StaticClient implements RunClient {
  readonly writable = false;
  activeLaneId: string | null = null;
  activeRunId: string | null = null;
  constructor(private readonly doc: RunDocument) {}
  async listRuns(): Promise<RunSummary[]> {
    return [];
  }
  async createRun(): Promise<CreateRunResponse> {
    throw new ReadOnlyError();
  }
  async getRun() {
    return this.doc;
  }
  async getLayout() {
    return { view: "default", nodes: {} };
  }
  async saveLayout(layout: WebLayout) {
    return layout;
  }
  async addStep(): Promise<AddStepResponse> {
    throw new ReadOnlyError();
  }
  async attach(): Promise<void> {
    throw new ReadOnlyError();
  }
  async cut(): Promise<void> {
    throw new ReadOnlyError();
  }
  async uncut(): Promise<void> {
    throw new ReadOnlyError();
  }
  async reparent(): Promise<AddStepResponse> {
    throw new ReadOnlyError();
  }
  async createLane(): Promise<CreateLaneResponse> {
    throw new ReadOnlyError();
  }
  async getExtensions() {
    return { extensions: [] };
  }
  async enableExtension(): Promise<void> {
    throw new ReadOnlyError();
  }
  async disableExtension(): Promise<void> {
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
