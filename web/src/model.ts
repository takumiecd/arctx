// Small read helpers over a RunDocument: payload lookups and graph labeling.

import type { RecordProvenance, RunDocument, RunGroup, RunPayload } from "./types";
import { payloadDisplayFor } from "./payloadExtensions";

export type LaneColorOverrides = Record<string, string>;

export interface LaneColors {
  laneColor: string;
  laneBg: string;
}

export interface LaneOption {
  lane_id: string;
  group_id: string;
  label: string;
}

export function payloadsForNode(doc: RunDocument, nodeId: string): RunPayload[] {
  return doc.payloads.filter((p) => p.target_kind === "node" && p.target_id === nodeId);
}

export function payloadsForStep(doc: RunDocument, stepId: string): RunPayload[] {
  return doc.payloads.filter((p) => p.target_kind === "step" && p.target_id === stepId);
}

// Whether a record is currently *directly* cut (a CutPayload on it that has not
// been superseded by a later UncutPayload). Mirrors the backend's last-marker-
// wins rule (arctx.core.cuts); payloads are scanned in document order. Only a
// directly-cut record can be uncut — inactivity inherited from a cut ancestor
// is not directly reversible.
export function isDirectlyCut(
  doc: RunDocument,
  recordId: string,
  kind: "node" | "step",
): boolean {
  let cut = false;
  for (const p of doc.payloads) {
    if (p.target_id !== recordId || p.target_kind !== kind) continue;
    if (p.payload_type === "cut") cut = true;
    else if (p.payload_type === "uncut") cut = false;
  }
  return cut;
}

// The text of a node's SummaryPayload (payload_type "summary"), if any. A
// summary is a descriptive context snapshot used for history truncation /
// hand-off; it never changes the validity of the node or its descendants.
export function nodeSummaryText(doc: RunDocument, nodeId: string): string | null {
  for (const p of payloadsForNode(doc, nodeId)) {
    if (p.payload_type === "summary") {
      const text = typeof p.text === "string" ? p.text.trim() : "";
      return text || "(summary)";
    }
  }
  return null;
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

export function laneOptions(doc: RunDocument): LaneOption[] {
  const options = new Map<string, LaneOption>();
  for (const lane of [...(doc.work_sessions ?? []), ...(doc.lanes ?? [])]) {
    const laneId = laneIdOf(lane);
    if (!laneId) continue;
    options.set(laneId, {
      lane_id: laneId,
      group_id: `lane:${laneId}`,
      label: lane.name || laneId,
    });
  }
  for (const group of laneGroups(doc)) {
    const laneId = group.lane_id;
    if (!laneId) continue;
    options.set(laneId, {
      lane_id: laneId,
      group_id: group.group_id,
      label: group.label,
    });
  }
  return [...options.values()];
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
  const session = [...(doc.work_sessions ?? []), ...(doc.lanes ?? [])].find(
    (s) => laneIdOf(s) === laneId,
  );
  return session?.name || laneId;
}

function laneIdOf(lane: { work_session_id?: string; lane_id?: string }): string | null {
  return lane.work_session_id || lane.lane_id || null;
}

export function laneColorIndex(doc: RunDocument, laneId: string): number {
  const ids = laneOptions(doc).map((lane) => lane.lane_id);
  const index = ids.indexOf(laneId);
  return index >= 0 ? index % 8 : 0;
}

export function laneColors(
  doc: RunDocument,
  laneId: string,
  overrides: LaneColorOverrides = {},
  dark = false,
): LaneColors {
  const override = normalizeHexColor(overrides[laneId]);
  if (override) {
    return { laneColor: override, laneBg: dark ? shadeHexColor(override) : tintHexColor(override) };
  }
  const palette = dark ? LANE_COLORS_DARK : LANE_COLORS;
  const [laneColor, laneBg] = palette[laneColorIndex(doc, laneId)];
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

const LANE_COLORS_DARK = [
  ["#3b82f6", "#172554"],
  ["#10b981", "#064e3b"],
  ["#eab308", "#422006"],
  ["#ef4444", "#450a0a"],
  ["#8b5cf6", "#2e1065"],
  ["#06b6d4", "#164e63"],
  ["#ec4899", "#500724"],
  ["#6366f1", "#1e1b4b"],
] as const;



function normalizeHexColor(color: string | undefined): string | null {
  if (!color || !/^#[0-9a-fA-F]{6}$/.test(color)) return null;
  return color.toLowerCase();
}

function tintHexColor(color: string): string {
  const channels = [1, 3, 5].map((start) => Number.parseInt(color.slice(start, start + 2), 16));
  const tinted = channels.map((channel) => Math.round(channel + (255 - channel) * 0.86));
  return `#${tinted.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

function shadeHexColor(color: string): string {
  const base = [15, 23, 42]; // #0f172a
  const channels = [1, 3, 5].map((start) => Number.parseInt(color.slice(start, start + 2), 16));
  const shaded = channels.map((ch, i) => Math.round(base[i] + (ch - base[i]) * 0.22));
  return `#${shaded.map((ch) => Math.max(0, Math.min(255, ch)).toString(16).padStart(2, "0")).join("")}`;
}

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
