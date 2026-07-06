// Pure helpers shared across panel modules: JSON parsing for form content,
// lane-adoption request shaping, and detail-unit / attach-target derivation
// from a selection.

import type { RunDocument } from "../types";
import type { AdoptMode, AttachTarget, BulkSelection, DetailUnit, RecordSelection } from "./types";

export function parseJson(raw: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("content must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

export function adoptLaneRequest(unit: DetailUnit, laneId: string, mode: AdoptMode) {
  const base = {
    lane_id: laneId,
    reason: "web lane adoption",
  };
  if (mode === "history") {
    return { ...base, history_node_id: unit.outputNodeId };
  }
  if (mode === "reachable") {
    return { ...base, reachable_node_id: unit.outputNodeId };
  }
  if (mode === "lane_head") {
    return { ...base, lane_head_node_id: unit.outputNodeId };
  }
  if (mode === "lane_tail") {
    return { ...base, lane_tail_node_id: unit.outputNodeId };
  }
  return { ...base, record_ids: explicitAdoptRecordIds(unit) };
}

export function explicitAdoptRecordIds(unit: DetailUnit): string[] {
  if (unit.stepId) {
    return [unit.stepId, unit.outputNodeId].filter(Boolean);
  }
  return [unit.outputNodeId];
}

export function explicitAdoptLabel(unit: DetailUnit): string {
  return unit.stepId ? "selected unit (step + output)" : "selected node only";
}

export function selectedRecordIds(selection: BulkSelection): string[] {
  return [...new Set(selection.records.map((record) => record.id))];
}

export function laneAdoptionRecordIds(selection: BulkSelection, doc: RunDocument): string[] {
  const ids: string[] = [];
  for (const record of selection.records) {
    if (record.kind === "node") {
      const producer = doc.steps.find((step) => step.output_node_id === record.id);
      if (producer) ids.push(producer.step_id);
      ids.push(record.id);
    } else {
      ids.push(record.id);
      const step = doc.steps.find((entry) => entry.step_id === record.id);
      if (step?.output_node_id) ids.push(step.output_node_id);
    }
  }
  return [...new Set(ids)];
}

export function visibleRecordIds(ids: string[]): string[] {
  return ids.slice(0, 24);
}

export function detailUnitFor(doc: RunDocument, selection: RecordSelection): DetailUnit {
  if (selection.kind === "step") {
    const step = doc.steps.find((entry) => entry.step_id === selection.id);
    return {
      stepId: step?.step_id ?? selection.id,
      outputNodeId: step?.output_node_id ?? "",
      selected: selection,
    };
  }
  const producer = doc.steps.find((step) => step.output_node_id === selection.id);
  return {
    stepId: producer?.step_id ?? null,
    outputNodeId: selection.id,
    selected: selection,
  };
}

export function attachTargetsFor(unit: DetailUnit): AttachTarget[] {
  if (!unit.stepId) {
    return [
      {
        key: "node",
        label: `node (${unit.outputNodeId.slice(0, 8)})`,
        selection: { kind: "node", id: unit.outputNodeId },
      },
    ];
  }
  const targets: AttachTarget[] = [
    {
      key: "step",
      label: `step (${unit.stepId.slice(0, 8)})`,
      selection: { kind: "step", id: unit.stepId },
    },
  ];
  if (unit.outputNodeId) {
    targets.push({
      key: "output-node",
      label: `output node note (${unit.outputNodeId.slice(0, 8)})`,
      selection: { kind: "node", id: unit.outputNodeId },
    });
  }
  return targets;
}
