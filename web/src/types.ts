// TypeScript mirror of the `arctx export --format json` document
// (arctx.core.run.export.json_document). This is the GUI data contract; keep it
// in sync with that Python function.

export interface RunNode {
  node_id: string;
  metadata: Record<string, unknown>;
  // Cut, or downstream of a cut. Precomputed by the backend.
  inactive: boolean;
  // This record carries an effective cut marker of its own. Key the "uncut"
  // control on this, never on re-deriving supersession from `payloads`.
  directly_cut: boolean;
}

export interface RunStep {
  step_id: string;
  input_node_ids: string[];
  output_node_id: string;
  metadata: Record<string, unknown>;
  inactive: boolean;
  directly_cut: boolean;
}

// Payloads are open-ended: every payload has these keys, plus type-specific
// fields (e.g. `type`, `content`, `reason`).
export interface RunPayload {
  payload_id: string;
  payload_type: string;
  target_kind: "node" | "step";
  target_id: string;
  type?: string;
  content?: Record<string, unknown>;
  reason?: string | null;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

// An asset is a reference to a git object — `(commit, path)` where `path` is
// repo-root-relative and may be a file or a directory. Nothing is copied: the
// serve layer resolves content at request time via
//   GET /asset?payload_id=…            reference + resolution status
//   GET /asset/entries?payload_id=…&path=…   directory listing
//   GET /asset/content?payload_id=…&path=…   file content (utf-8 or base64)
//   GET /asset/raw?payload_id=…&path=…       file bytes
// Per the "absent = self" convention there is no repo field.
export interface RunAssetPayload extends RunPayload {
  payload_type: "asset";
  commit: string;
  path: string;
  title?: string | null;
}

export function isAssetPayload(payload: RunPayload): payload is RunAssetPayload {
  return payload.payload_type === "asset";
}

// A git_change record stores facts only — the commit hashes it points at and
// the branch it was made on. Diff stats, commit subjects, file lists, and patch
// text are NOT in the export document: they are derived from the repository at
// read time (POST /web/ext/git/diff). A commit missing from the reader's clone
// comes back with `available: false` and a `note` marker rather than an error.
export interface RunGitChangePayload extends RunPayload {
  payload_type: "git_change";
  target_kind: "step";
  branch: string;
  head_commit: string;
  commits: string[];
}

export function isGitChangePayload(payload: RunPayload): payload is RunGitChangePayload {
  return payload.payload_type === "git_change";
}

// A trial (optimize extension) is one scored attempt on a Step: the config
// that was tried and the metric values that came out. `tables` are plain
// shared names — there is no table record. Which tables exist, their columns,
// column kinds, and best rows are all derived from the rows at read time
// (see trials.ts), mirroring arctx/ext/optimize/tables.py.
export interface RunTrialPayload extends RunPayload {
  payload_type: "trial";
  target_kind: "step";
  tables: string[];
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
  title?: string | null;
}

export function isTrialPayload(payload: RunPayload): payload is RunTrialPayload {
  return payload.payload_type === "trial";
}

// Response shape of POST /web/ext/git/diff — entirely derived, never stored.
export interface GitChangeDiff {
  step_id: string;
  repo_path: string;
  head_commit: string;
  branch: string;
  available: boolean;
  note: string | null;
  subject: string;
  files: string[];
  diff_stat: { files_changed: number; insertions: number; deletions: number };
  diff: string;
  truncated: boolean;
  byte_count: number;
}

export interface AssetResolution {
  status:
    | "ok"
    | "missing_commit"
    | "missing_path"
    | "no_repository"
    | "unknown_payload"
    | "not_an_asset"
    | "git_error";
  kind: "blob" | "tree" | null;
  content_type?: string | null;
  message?: string;
}

// GET /asset — the stored reference plus whether it resolves in this clone.
export interface AssetView {
  asset: {
    payload_id: string;
    target_kind: "node" | "step";
    target_id: string;
    commit: string;
    path: string;
    title?: string | null;
  };
  resolution: AssetResolution;
}

// GET /asset/entries — one level of a tree asset.
export interface AssetEntriesResponse {
  payload_id: string;
  commit: string;
  path: string;
  entries: AssetTreeEntry[];
}

// GET /asset/content — a blob, inline as utf-8 text or base64 bytes.
export interface AssetContentResponse {
  payload_id: string;
  commit: string;
  path: string;
  content_type: string;
  size: number;
  encoding: "utf-8" | "base64";
  content: string;
}

export interface AssetTreeEntry {
  name: string;
  path: string;
  kind: "blob" | "tree" | "commit";
  mode: string;
  oid: string;
  size: number | null;
}

export interface RunLane {
  lane_id: string;
  run_id: string;
  created_by: string;
  started_at?: string | null;
  closed_at?: string | null;
  status?: string;
  metadata?: Record<string, unknown>;
  name?: string | null;
}

export interface RunWorkEvent {
  event_id: string;
  run_id: string;
  lane_id: string;
  user_id: string;
  event_type: string;
  target_kind?: string | null;
  target_id?: string | null;
  created_records?: string[];
  summary?: string | null;
  data?: Record<string, unknown>;
  created_at?: string | null;
  seq?: number | null;
}

export interface RecordProvenance {
  record_id: string;
  lane_id: string;
  lane_name?: string | null;
  user_id: string;
  event_id: string;
  event_type: string;
  created_at?: string | null;
}

export interface RunGroup {
  group_id: string;
  kind: "lane" | string;
  lane_id?: string;
  label: string;
  node_ids: string[];
  step_ids: string[];
  color_key?: string;
}

export interface LaneBoundary {
  from_lane_id: string;
  to_lane_id: string;
  step_id: string;
  input_node_id: string;
  output_node_id: string;
}

export interface LaneEdgeSummary {
  lane_id: string;
  node_id: string;
  payload_id: string;
  text: string;
  metadata?: {
    format?: "markdown" | "html" | "text" | string;
    [key: string]: unknown;
  };
}

export interface RunDocument {
  arctx_export_version: number;
  run_id: string;
  root_node_id: string;
  counts: { nodes: number; steps: number; payloads: number };
  nodes: RunNode[];
  steps: RunStep[];
  payloads: RunPayload[];
  lanes?: RunLane[];
  work_events?: RunWorkEvent[];
  record_provenance?: Record<string, RecordProvenance>;
  groups?: RunGroup[];
  lane_boundaries?: LaneBoundary[];
  lane_edge_summaries?: LaneEdgeSummary[];
  current_lane_id?: string;
  current_lane_name?: string | null;
}

export interface WebLayout {
  view: string;
  nodes: Record<string, { x: number; y: number }>;
}

// One entry of the run picker (GET /runs). Mirrors `store.list_runs()`.
export interface RunSummary {
  run_id: string;
  requirement_id?: string;
  target_type?: string;
  target_id?: string;
}

export interface RunsResponse {
  runs: RunSummary[];
  current_run_id?: string;
}

export interface CreateRunRequest {
  run_id: string;
  requirement_id?: string;
  target_type?: string;
  target_id?: string;
}

export interface CreateRunResponse {
  run: RunSummary;
  run_id: string;
  root_node_id: string;
}

// ----- write request bodies (POST routes of `arctx serve`) -----

export interface AddStepRequest {
  input_node_ids: string[];
  // When set, the step connects into this existing (producer-less) node instead
  // of minting a new output node.
  output_node_id?: string;
  type?: string;
  content?: Record<string, unknown>;
  payload_type?: string;
}

export interface AddStepResponse {
  step: {
    kind: "step";
    id: string;
    step_id: string;
    input_node_ids: string[];
    output_node_id: string;
    metadata: Record<string, unknown>;
  };
}

export interface AttachRequest {
  target_id: string;
  target_kind: "node" | "step";
  type?: string;
  content?: Record<string, unknown>;
  payload_type?: string;
}

export interface CutRequest {
  target_id: string;
  target_kind: "node" | "step";
  reason?: string;
}

// Reverse a cut (append-only). Mirrors `POST /uncut`.
export interface UncutRequest {
  target_id: string;
  target_kind: "node" | "step";
  reason?: string;
}

// Re-parent a node onto new inputs (append-only). Mirrors `POST /reparent`:
// appends a new producing step and cuts the previously-active producer.
export interface ReparentRequest {
  node_id: string;
  input_node_ids: string[];
  type?: string;
  content?: Record<string, unknown>;
  payload_type?: string;
  reason?: string;
}

export interface CreateLaneRequest {
  name: string;
  metadata?: Record<string, unknown>;
}

export interface CreateLaneResponse {
  lane: RunLane;
}

export interface ExtensionItem {
  name: string;
  enabled: boolean;
}

export interface ExtensionsResponse {
  extensions: ExtensionItem[];
}
