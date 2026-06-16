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

export interface RunDocument {
  arctx_export_version: number;
  run_id: string;
  root_node_id: string;
  counts: { nodes: number; steps: number; payloads: number };
  nodes: RunNode[];
  steps: RunStep[];
  payloads: RunPayload[];
  repos: RunRepo[];
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

export interface CutRequest {
  target_id: string;
  target_kind: "node" | "step";
  reason?: string;
}
