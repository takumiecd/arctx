// "Flow" tab content: the selected unit's input/next neighbors, rendered as
// clickable cards so the user can walk the graph from the panel.

import type { Selection } from "../Graph";
import { nodeLabel, payloadsForNode, payloadsForStep, stepType } from "../model";
import { payloadDisplayFor } from "../payloadExtensions";
import type { RunDocument, RunPayload } from "../types";
import type { DetailUnit, RecordSelection } from "./types";

export function SelectionContext({
  doc,
  unit,
  onSelect,
}: {
  doc: RunDocument;
  unit: DetailUnit;
  onSelect: (sel: Selection) => void;
}) {
  const nextSteps = doc.steps.filter((step) => step.input_node_ids.includes(unit.outputNodeId));
  if (unit.stepId) {
    const step = doc.steps.find((entry) => entry.step_id === unit.stepId);
    if (!step) return <p className="muted">step not found</p>;
    return (
      <section className="record-context">
        <h3>unit flow</h3>
        <div className="unit-flow">
          <div className="flow-group">
            <div className="flow-heading">
              <span className="flow-label">inputs</span>
              <span className="flow-count">{step.input_node_ids.length}</span>
            </div>
            <div className="flow-list">
              {step.input_node_ids.map((nodeId) => (
                <UnitCard
                  key={nodeId}
                  doc={doc}
                  nodeId={nodeId}
                  onSelect={onSelect}
                />
              ))}
            </div>
          </div>
          <div className="flow-group">
            <div className="flow-heading">
              <span className="flow-label">next</span>
              <span className="flow-count">{nextSteps.length}</span>
            </div>
            <div className="flow-list">
              {nextSteps.length === 0 ? (
                <p className="flow-empty">no next units</p>
              ) : (
                nextSteps.map((nextStep) => (
                  <UnitCard
                    key={nextStep.step_id}
                    doc={doc}
                    nodeId={nextStep.output_node_id}
                    stepId={nextStep.step_id}
                    onSelect={onSelect}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="record-context">
      <h3>unit flow</h3>
      <div className="unit-flow">
        <div className="flow-group">
          <div className="flow-heading">
            <span className="flow-label">next</span>
            <span className="flow-count">{nextSteps.length}</span>
          </div>
          <div className="flow-list">
            {nextSteps.length === 0 ? (
              <p className="flow-empty">no next units</p>
            ) : (
              nextSteps.map((step) => (
                <UnitCard
                  key={step.step_id}
                  doc={doc}
                  nodeId={step.output_node_id}
                  stepId={step.step_id}
                  onSelect={onSelect}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function UnitCard({
  doc,
  nodeId,
  stepId,
  onSelect,
}: {
  doc: RunDocument;
  nodeId: string;
  stepId?: string | null;
  onSelect: (sel: Selection) => void;
}) {
  const producer = stepId
    ? doc.steps.find((step) => step.step_id === stepId)
    : doc.steps.find((step) => step.output_node_id === nodeId);
  const unitStepId = producer?.step_id ?? null;
  const stepPayloads = unitStepId ? payloadsForStep(doc, unitStepId) : [];
  const nodePayloads = payloadsForNode(doc, nodeId);
  const stepSummary = firstPayloadSummary(doc, stepPayloads);
  const nodeSummary = firstPayloadSummary(doc, nodePayloads);
  const title = unitStepId ? stepType(doc, unitStepId) : nodeLabel(doc, nodeId);
  const target: RecordSelection = unitStepId
    ? { kind: "step", id: unitStepId }
    : { kind: "node", id: nodeId };
  return (
    <button
      className="unit-card"
      type="button"
      title={unitStepId ? `step ${unitStepId} -> node ${nodeId}` : `node ${nodeId}`}
      onClick={() => onSelect(target)}
    >
      <span className="unit-card-title">{title}</span>
      <span className="unit-card-ids">
        {unitStepId && <code>s:{unitStepId.slice(0, 8)}</code>}
        <code>n:{nodeId.slice(0, 8)}</code>
      </span>
      {stepSummary && <span className="unit-card-summary">{stepSummary}</span>}
      {nodeSummary && (
        <span className="unit-card-summary node-note">
          node: {nodeSummary}
        </span>
      )}
    </button>
  );
}

function firstPayloadSummary(doc: RunDocument, payloads: RunPayload[]): string | null {
  for (const payload of payloads) {
    if (payload.payload_type === "cut") continue;
    const display = payloadDisplayFor(payload, doc);
    const summary = display.summary || display.graphLabel || display.title;
    if (summary && summary.trim()) {
      const normalized = summary.replace(/\s+/g, " ").trim();
      return normalized.length > 86 ? `${normalized.slice(0, 85)}...` : normalized;
    }
  }
  return null;
}
