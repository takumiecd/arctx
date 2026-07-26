// Pure helpers shared across panel modules: JSON parsing for form content,
// detail-unit / attach-target derivation
// from a selection.

import type { RunDocument } from "../types";
import type { AttachTarget, BulkSelection, DetailUnit, RecordSelection } from "./types";

export function parseJson(raw: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("content must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

export function selectedRecordIds(selection: BulkSelection): string[] {
  return [...new Set(selection.records.map((record) => record.id))];
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
