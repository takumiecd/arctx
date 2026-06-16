import type { RunDocument, RunPayload } from "./types";

export interface PayloadField {
  label: string;
  value: unknown;
}

export interface PayloadSection {
  title: string;
  kind?: "json" | "list" | "text" | "table" | "markdown" | "diff" | "image";
  value: unknown;
  collapsed?: boolean;
}

export interface PayloadMedia {
  kind: "image";
  src: string;
  alt?: string;
  caption?: string;
}

export interface PayloadDisplay {
  title: string;
  summary?: string | null;
  graphLabel?: string | null;
  media?: PayloadMedia[];
  fields?: PayloadField[];
  sections?: PayloadSection[];
  raw?: boolean;
}

export interface PayloadRenderContext {
  doc: RunDocument;
}

export type PayloadRenderer = (
  payload: RunPayload,
  context: PayloadRenderContext,
) => PayloadDisplay | null | undefined;

export interface PayloadElementRegistration {
  tagName: string;
  fallbackRenderer?: PayloadRenderer;
}

export interface ArctxWebExtensionApi {
  registerPayloadRenderer: (key: string, renderer: PayloadRenderer) => void;
  registerPayloadElement: (key: string, registration: PayloadElementRegistration) => void;
}

export type ArctxWebExtensionInstaller = (api: ArctxWebExtensionApi) => void;

declare global {
  interface Window {
    arctxWeb?: ArctxWebExtensionApi;
    arctxWebExtensions?: ArctxWebExtensionInstaller[];
  }
}

const renderers = new Map<string, PayloadRenderer>();
const elements = new Map<string, PayloadElementRegistration>();

export function registerPayloadRenderer(key: string, renderer: PayloadRenderer): void {
  renderers.set(key, renderer);
}

export function registerPayloadElement(
  key: string,
  registration: PayloadElementRegistration,
): void {
  if (!isCustomElementName(registration.tagName)) {
    console.warn(`invalid arctx-web payload element tag: ${registration.tagName}`);
    return;
  }
  elements.set(key, registration);
  if (registration.fallbackRenderer) {
    renderers.set(key, registration.fallbackRenderer);
  }
}

export function installGlobalPayloadExtensionApi(): void {
  const api: ArctxWebExtensionApi = { registerPayloadRenderer, registerPayloadElement };
  window.arctxWeb = api;
  const queued = window.arctxWebExtensions ?? [];
  window.arctxWebExtensions = [];
  for (const install of queued) {
    install(api);
  }
}

export function payloadDisplayFor(payload: RunPayload, doc: RunDocument): PayloadDisplay {
  const keys = rendererKeys(payload);
  for (const key of keys) {
    const renderer = renderers.get(key);
    if (!renderer) continue;
    const display = renderer(payload, { doc });
    if (display) return display;
  }
  return fallbackDisplay(payload);
}

export function payloadElementFor(payload: RunPayload): PayloadElementRegistration | null {
  for (const key of rendererKeys(payload)) {
    const registration = elements.get(key);
    if (registration) return registration;
  }
  return null;
}

function rendererKeys(payload: RunPayload): string[] {
  const keys: string[] = [];
  if (typeof payload.type === "string" && payload.type) {
    keys.push(`${payload.payload_type}:${payload.type}`);
  }
  keys.push(payload.payload_type);
  return keys;
}

function isCustomElementName(tagName: string): boolean {
  return /^[a-z][a-z0-9]*-[a-z0-9-]+$/.test(tagName);
}

function fallbackDisplay(payload: RunPayload): PayloadDisplay {
  return {
    title: payload.payload_type,
    summary: typeof payload.type === "string" && payload.type ? payload.type : null,
    fields: [
      { label: "payload", value: payload.payload_id },
      { label: "target", value: payload.target_id },
    ],
    sections: [{ title: "raw", kind: "json", value: payload }],
    raw: true,
  };
}

function genericPayloadDisplay(payload: RunPayload): PayloadDisplay {
  const title = typeof payload.type === "string" && payload.type ? payload.type : payload.payload_type;
  const fields: PayloadField[] = [{ label: "type", value: title }];
  const sections: PayloadSection[] = [];
  if (payload.content && Object.keys(payload.content).length > 0) {
    sections.push({ title: "content", kind: "json", value: payload.content });
  }
  if (payload.metadata && Object.keys(payload.metadata).length > 0) {
    sections.push({ title: "metadata", kind: "json", value: payload.metadata });
  }
  const text = payload.content?.text;
  const label = genericContentLabel(payload);
  return {
    title,
    summary: typeof text === "string" && text.trim() ? text.trim() : null,
    graphLabel: label,
    fields,
    sections,
  };
}

function cutDisplay(payload: RunPayload): PayloadDisplay {
  return {
    title: "cut",
    summary: typeof payload.reason === "string" && payload.reason ? payload.reason : "inactive marker",
    fields: [
      { label: "target", value: payload.target_id },
      { label: "kind", value: payload.target_kind },
    ],
  };
}

function joinDisplay(payload: RunPayload): PayloadDisplay {
  const joined = Array.isArray(payload.joined_views) ? payload.joined_views : [];
  return {
    title: "join",
    summary: `${joined.length} joined view(s)`,
    fields: [{ label: "joined_views", value: joined }],
  };
}

function gitChangeDisplay(payload: RunPayload, { doc }: PayloadRenderContext): PayloadDisplay {
  const diff = objectValue(payload.diff_summary);
  const commits = Array.isArray(payload.commit_log) ? payload.commit_log : [];
  const repoId = stringValue(payload.repo_id);
  const fields: PayloadField[] = [
    { label: "branch", value: payload.branch },
    { label: "head", value: shortSha(payload.head_commit) },
    { label: "files", value: diff.files_changed ?? 0 },
    { label: "+/-", value: `+${diff.insertions ?? 0} -${diff.deletions ?? 0}` },
  ];
  if (repoId) {
    fields.unshift({ label: "repo", value: repoLabel(doc, repoId) });
  }
  return {
    title: "git change",
    summary: commitSubject(commits) ?? stringValue(payload.head_commit),
    graphLabel: commitSubject(commits) ?? shortSha(payload.head_commit),
    fields,
    sections: commits.length > 0 ? [{ title: "commits", kind: "list", value: commits }] : [],
  };
}

function branchDisplay(payload: RunPayload, { doc }: PayloadRenderContext): PayloadDisplay {
  const repoId = stringValue(payload.repo_id);
  const fields: PayloadField[] = [{ label: "branch", value: payload.branch }];
  if (repoId) fields.unshift({ label: "repo", value: repoLabel(doc, repoId) });
  return { title: "branch", summary: stringValue(payload.branch), fields };
}

function revertDisplay(payload: RunPayload): PayloadDisplay {
  return {
    title: "revert",
    summary: shortSha(payload.reverted_commit),
    graphLabel: `revert ${shortSha(payload.reverted_commit)}`,
    fields: [
      { label: "step", value: payload.reverted_step },
      { label: "commit", value: shortSha(payload.reverted_commit) },
    ],
  };
}

function cherryPickDisplay(payload: RunPayload): PayloadDisplay {
  return {
    title: "cherry-pick",
    summary: shortSha(payload.source_commit),
    graphLabel: `cherry-pick ${shortSha(payload.source_commit)}`,
    fields: [
      { label: "source_step", value: payload.source_step },
      { label: "source_commit", value: shortSha(payload.source_commit) },
    ],
  };
}

function mergeDisplay(payload: RunPayload): PayloadDisplay {
  const from = stringValue(payload.merged_from);
  const into = stringValue(payload.merged_into);
  return {
    title: "merge",
    summary: `${from} -> ${into}`,
    graphLabel: `merge ${from}`,
    fields: [
      { label: "from", value: from },
      { label: "into", value: into },
    ],
  };
}

function commandRunDisplay(payload: RunPayload): PayloadDisplay {
  const command = Array.isArray(payload.command) ? payload.command.map(String).join(" ") : "";
  const sections: PayloadSection[] = [];
  if (payload.stdout) sections.push({ title: "stdout", kind: "text", value: payload.stdout });
  if (payload.stderr) sections.push({ title: "stderr", kind: "text", value: payload.stderr });
  return {
    title: "command",
    summary: command,
    graphLabel: command,
    fields: [
      { label: "exit", value: payload.exit_code ?? 0 },
      { label: "duration_ms", value: payload.duration_ms ?? 0 },
      { label: "cwd", value: payload.cwd ?? "" },
    ],
    sections,
  };
}

function objectValue(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function genericContentLabel(payload: RunPayload): string | null {
  const content = payload.content;
  if (!content) return null;
  for (const key of ["message", "title", "summary", "text", "name", "proposal", "result"]) {
    const value = content[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function shortSha(value: unknown): string {
  const sha = stringValue(value);
  return sha ? sha.slice(0, 12) : "";
}

function repoLabel(doc: RunDocument, repoId: string): string {
  const repo = doc.repos.find((entry) => entry.repo_id === repoId);
  return repo?.slug ?? repoId;
}

function commitSubject(commits: unknown[]): string | null {
  const first = commits[0];
  if (typeof first !== "object" || first === null || Array.isArray(first)) return null;
  const subject = (first as Record<string, unknown>).subject;
  return typeof subject === "string" && subject ? subject : null;
}

registerPayloadRenderer("node_payload", genericPayloadDisplay);
registerPayloadRenderer("step_payload", genericPayloadDisplay);
registerPayloadRenderer("cut", cutDisplay);
registerPayloadRenderer("join", joinDisplay);
registerPayloadRenderer("git_change", gitChangeDisplay);
registerPayloadRenderer("branch", branchDisplay);
registerPayloadRenderer("revert", revertDisplay);
registerPayloadRenderer("cherry_pick", cherryPickDisplay);
registerPayloadRenderer("merge", mergeDisplay);
registerPayloadRenderer("command_run", commandRunDisplay);
