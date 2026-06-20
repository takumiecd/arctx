// Small read helpers over a RunDocument: payload lookups and graph labeling.

import type { RecordProvenance, RunDocument, RunGroup, RunPayload } from "./types";
import { payloadDisplayFor } from "./payloadExtensions";

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

export function nodeLabel(doc: RunDocument, nodeId: string): string {
  if (nodeId === doc.root_node_id) return "root";

  const producer = doc.steps.find((s) => s.output_node_id === nodeId);
  if (producer) {
    const stepPayload = stepActionPayload(payloadsForStep(doc, producer.step_id));
    if (stepPayload) {
      return compactLabel(graphLabel(doc, stepPayload));
    }
    const label = stepType(doc, producer.step_id);
    return label === "step" ? "output" : compactLabel(label);
  }

  const nodePayload = firstMeaningfulPayload(payloadsForNode(doc, nodeId));
  if (nodePayload) {
    return compactLabel(graphLabel(doc, nodePayload));
  }

  return "node";
}

export function laneGroups(doc: RunDocument): RunGroup[] {
  return (doc.groups ?? []).filter((group) => group.kind === "lane" && group.lane_id);
}

export function provenanceFor(doc: RunDocument, recordId: string): RecordProvenance | null {
  return doc.record_provenance?.[recordId] ?? null;
}

export function laneIdForRecord(doc: RunDocument, recordId: string): string | null {
  return provenanceFor(doc, recordId)?.lane_id ?? null;
}

export function laneLabel(doc: RunDocument, laneId: string): string {
  const group = laneGroups(doc).find((g) => g.lane_id === laneId);
  if (group?.label) return group.label;
  const session = (doc.work_sessions ?? []).find((s) => s.work_session_id === laneId);
  return session?.name || laneId;
}

export function laneColorIndex(doc: RunDocument, laneId: string): number {
  const ids = laneGroups(doc).map((group) => group.lane_id).filter(Boolean) as string[];
  const index = ids.indexOf(laneId);
  return index >= 0 ? index % 8 : 0;
}

export function laneColors(doc: RunDocument, laneId: string): { laneColor: string; laneBg: string } {
  const [laneColor, laneBg] = LANE_COLORS[laneColorIndex(doc, laneId)];
  return { laneColor, laneBg };
}

const LANE_COLORS = [
  ["#2563eb", "#dbeafe"],
  ["#059669", "#d1fae5"],
  ["#ca8a04", "#fef3c7"],
  ["#dc2626", "#fee2e2"],
  ["#7c3aed", "#ede9fe"],
  ["#0891b2", "#cffafe"],
  ["#db2777", "#fce7f3"],
  ["#4f46e5", "#e0e7ff"],
] as const;

function firstMeaningfulPayload(payloads: RunPayload[]): RunPayload | null {
  return payloads.find((p) => p.payload_type !== "cut") ?? null;
}

function stepActionPayload(payloads: RunPayload[]): RunPayload | null {
  const priority = [
    "git_change",
    "command_run",
    "merge",
    "join",
    "revert",
    "cherry_pick",
    "step_payload",
  ];
  for (const payloadType of priority) {
    const payload = payloads.find((p) => p.payload_type === payloadType && isInformativeStepPayload(p));
    if (payload) return payload;
  }
  return payloads.find((p) => p.payload_type !== "cut" && isInformativeStepPayload(p)) ?? null;
}

function isInformativeStepPayload(payload: RunPayload): boolean {
  if (payload.payload_type !== "step_payload") return true;
  const type = typeof payload.type === "string" ? payload.type : "";
  const content = payload.content ?? {};
  return type !== "step" || Object.keys(content).length > 0;
}

function graphLabel(doc: RunDocument, payload: RunPayload): string {
  const display = payloadDisplayFor(payload, doc);
  if (display.graphLabel && display.graphLabel.trim()) return display.graphLabel;
  if (display.summary && display.summary.trim()) return display.summary;
  if (typeof payload.type === "string" && payload.type) return payload.type;
  return display.title || payload.payload_type;
}

function compactLabel(label: string): string {
  const normalized = label.replace(/\s+/g, " ").trim();
  if (!normalized) return "node";
  return normalized.length > 28 ? `${normalized.slice(0, 27)}...` : normalized;
}
