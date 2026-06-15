// Small read helpers over a RunDocument: payload lookups and step labeling.

import type { RunDocument, RunPayload } from "./types";

export function payloadsForNode(doc: RunDocument, nodeId: string): RunPayload[] {
  return doc.payloads.filter((p) => p.target_kind === "node" && p.target_id === nodeId);
}

export function payloadsForStep(doc: RunDocument, stepId: string): RunPayload[] {
  return doc.payloads.filter((p) => p.target_kind === "step" && p.target_id === stepId);
}

// A step's display label: the `type` of its first step-targeting payload, else
// "step".
export function stepType(doc: RunDocument, stepId: string): string {
  for (const p of payloadsForStep(doc, stepId)) {
    if (typeof p.type === "string" && p.type) return p.type;
  }
  return "step";
}
