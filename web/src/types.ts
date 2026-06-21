// TypeScript mirror of the `arctx export --format json` document
// (arctx.core.run.export.json_document). This is the GUI data contract; keep it
// in sync with that Python function.

export interface RunNode {
  node_id: string;
  metadata: Record<string, unknown>;
  inactive: boolean;
}

export interface RunStep {
  step_id: string;
  input_node_ids: string[];
  output_node_id: string;
  metadata: Record<string, unknown>;
  inactive: boolean;
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
  asset_id?: string;
  filename?: string;
  mime_type?: string;
  size_bytes?: number;
  path?: string;
  [key: string]: unknown;
}

export interface RunRepo {
  repo_id: string;
  slug?: string;
  canonical?: string;
  remotes?: { kind: string; url: string }[];
  local_path?: string;
  [key: string]: unknown;
}

export interface RunWorkSession {
  work_session_id: string;
  run_id: string;
  user_id: string;
  parent_work_session_id?: string | null;
  started_at?: string | null;
  closed_at?: string | null;
  status?: string;
  metadata?: Record<string, unknown>;
  name?: string | null;
}

export interface RunWorkEvent {
  event_id: string;
  run_id: string;
  work_session_id: string;
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
  membership_kind?: "created" | "adopted" | string;
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

export interface RunDocument {
  arctx_export_version: number;
  run_id: string;
  root_node_id: string;
  counts: { nodes: number; steps: number; payloads: number };
  nodes: RunNode[];
  steps: RunStep[];
  payloads: RunPayload[];
  repos: RunRepo[];
  lanes?: RunWorkSession[];
  work_sessions?: RunWorkSession[];
  work_events?: RunWorkEvent[];
  record_provenance?: Record<string, RecordProvenance>;
  created_provenance?: Record<string, RecordProvenance>;
  groups?: RunGroup[];
  lane_boundaries?: LaneBoundary[];
  current_lane_id?: string;
  current_lane_name?: string | null;
}

export interface WebLayout {
  view: string;
  nodes: Record<string, { x: number; y: number }>;
}

// ----- write request bodies (POST routes of `arctx serve`) -----

export interface AddNodeRequest {
  type?: string;
  content?: Record<string, unknown>;
  payload_type?: string;
}

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

export interface UploadedArtifact {
  artifact_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  path: string;
}

export interface AttachAssetRequest {
  target_id: string;
  target_kind: "node" | "step";
  asset_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  path: string;
}

export interface VisibleAssetsResponse {
  from: string;
  assets: RunPayload[];
}

export interface CutRequest {
  target_id: string;
  target_kind: "node" | "step";
  reason?: string;
}

export interface CreateLaneRequest {
  name: string;
  metadata?: Record<string, unknown>;
}

export interface CreateLaneResponse {
  lane: RunWorkSession;
}

export interface AdoptLaneRequest {
  lane_id?: string;
  name?: string;
  record_ids?: string[];
  history_node_id?: string;
  reachable_node_id?: string;
  reason?: string;
}

export interface AdoptLaneResponse {
  lane_id: string;
  name?: string | null;
  adopted_record_ids: string[];
  count: number;
  mode: "explicit" | "history" | "reachable" | string;
  event_id: string;
}

export interface ExtensionItem {
  name: string;
  enabled: boolean;
}

export interface ExtensionsResponse {
  extensions: ExtensionItem[];
}
