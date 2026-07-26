// "Edit" tab body for a single node/step selection: add-step, reparent,
// attach-payload, and the cut/uncut danger zone. Split out of
// Panel.tsx's main render to keep that file from growing unbounded — this is
// the largest single piece of the writable-mode UI.

import type { UseMutationResult } from "@tanstack/react-query";

import type { Selection } from "../Graph";
import { isDirectlyCut } from "../model";
import type { RunDocument } from "../types";
import { PAYLOAD_SCHEMAS } from "./schemas";
import type {
  AttachPreset,
  AttachTarget,
  DetailUnit,
  RecordSelection,
} from "./types";

export function RecordEditForm({
  doc,
  unit,
  selection,
  error,
  stepType,
  setStepType,
  stepRawJsonMode,
  setStepRawJsonMode,
  stepContent,
  setStepContent,
  stepNoteText,
  setStepNoteText,
  stepJsonError,
  addStep,
  reparentInputs,
  setReparentInputs,
  reparent,
  attachTargets,
  attachTarget,
  setAttachTargetKey,
  attachPreset,
  setAttachPreset,
  formValues,
  setFormValues,
  customType,
  setCustomType,
  customContent,
  setCustomContent,
  jsonError,
  attach,
  uncut,
  cut,
  onSelect,
}: {
  doc: RunDocument;
  unit: DetailUnit;
  selection: RecordSelection;
  error: string | null;
  stepType: string;
  setStepType: (value: string) => void;
  stepRawJsonMode: boolean;
  setStepRawJsonMode: (value: boolean) => void;
  stepContent: string;
  setStepContent: (value: string) => void;
  stepNoteText: string;
  setStepNoteText: (value: string) => void;
  stepJsonError: string | null;
  addStep: UseMutationResult<unknown, Error, string>;
  reparentInputs: string;
  setReparentInputs: (value: string) => void;
  reparent: UseMutationResult<unknown, Error, { nodeId: string; inputs: string[]; type: string }>;
  attachTargets: AttachTarget[];
  attachTarget: AttachTarget;
  setAttachTargetKey: (value: string) => void;
  attachPreset: AttachPreset;
  setAttachPreset: (value: AttachPreset) => void;
  formValues: Record<string, any>;
  setFormValues: (updater: (prev: Record<string, any>) => Record<string, any>) => void;
  customType: string;
  setCustomType: (value: string) => void;
  customContent: string;
  setCustomContent: (value: string) => void;
  jsonError: string | null;
  attach: UseMutationResult<unknown, Error, AttachTarget>;
  uncut: UseMutationResult<unknown, Error, RecordSelection>;
  cut: UseMutationResult<unknown, Error, RecordSelection>;
  onSelect: (sel: Selection) => void;
}) {
  return (
    <section className="actions panel-edit-tabs">
      {error && <p className="error">{error}</p>}

      {unit.outputNodeId && (
        <div className="edit-section">
          <h3>add next step from output node</h3>
          <label>
            type
            <input value={stepType} onChange={(e) => setStepType(e.target.value)} />
          </label>

          <div style={{ margin: "8px 0" }}>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={stepRawJsonMode}
                onChange={(e) => setStepRawJsonMode(e.target.checked)}
                style={{ width: "auto", margin: 0 }}
              />
              Raw JSON content mode
            </label>
          </div>

          {stepRawJsonMode ? (
            <label>
              content (JSON)
              <textarea
                rows={3}
                value={stepContent}
                onChange={(e) => setStepContent(e.target.value)}
              />
            </label>
          ) : (
            <label>
              Step Message (Markdown supported)
              <textarea
                rows={3}
                placeholder="Describe this step..."
                value={stepNoteText}
                onChange={(e) => setStepNoteText(e.target.value)}
              />
            </label>
          )}
          {stepJsonError && <p className="error hint">{stepJsonError}</p>}
          <button
            disabled={addStep.isPending || (stepRawJsonMode && !!stepJsonError)}
            onClick={() => addStep.mutate(unit.outputNodeId)}
          >
            add step
          </button>
        </div>
      )}

      {unit.outputNodeId && unit.outputNodeId !== doc.root_node_id && (
        <div className="edit-section">
          <h3>reparent (rewire inputs)</h3>
          <p className="muted">
            Append a new producing step from these inputs and cut the old
            producer. The node and its descendants are kept.
          </p>
          <label>
            new input node ids (comma-separated)
            <input
              value={reparentInputs}
              placeholder="n_..., n_..."
              onChange={(e) => setReparentInputs(e.target.value)}
            />
          </label>
          <label>
            type
            <input value={stepType} onChange={(e) => setStepType(e.target.value)} />
          </label>
          <button
            disabled={reparent.isPending || reparentInputs.trim() === ""}
            onClick={() =>
              reparent.mutate({
                nodeId: unit.outputNodeId,
                inputs: reparentInputs
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
                type: stepType,
              })
            }
          >
            reparent
          </button>
        </div>
      )}

      <div className="edit-section">
        <h3>attach payload</h3>
        <label>
          target
          <select value={attachTarget.key} onChange={(e) => setAttachTargetKey(e.target.value)}>
            {attachTargets.map((target) => (
              <option key={target.key} value={target.key}>
                {target.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Preset Type
          <select
            value={attachPreset}
            onChange={(e) => setAttachPreset(e.target.value as AttachPreset)}
          >
            <option value="note">Note (Markdown)</option>
            <option value="git_change">Git Change (Git Integration)</option>
            <option value="diagram">Diagram (Mermaid / Graphviz)</option>
            <option value="command_run">Command Run (Execution Log)</option>
            <option value="custom">Custom JSON</option>
          </select>
        </label>

        {/* Dynamic Preset fields */}
        {attachPreset !== "custom" && PAYLOAD_SCHEMAS[attachPreset] && (
          <div className="dynamic-fields">
            {PAYLOAD_SCHEMAS[attachPreset].fields.map((field) => {
              const val = formValues[field.key] ?? "";
              const onChange = (v: any) => setFormValues((prev) => ({ ...prev, [field.key]: v }));

              return (
                <label key={field.key}>
                  {field.label}
                  {field.type === "textarea" ? (
                    <textarea
                      rows={field.key === "source" ? 6 : 3}
                      placeholder={field.placeholder}
                      value={val}
                      onChange={(e) => onChange(e.target.value)}
                    />
                  ) : field.type === "select" ? (
                    <select value={val} onChange={(e) => onChange(e.target.value)}>
                      {field.options && field.options(doc).map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={field.type}
                      placeholder={field.placeholder}
                      value={val}
                      onChange={(e) => onChange(field.type === "number" ? Number(e.target.value) : e.target.value)}
                    />
                  )}
                </label>
              );
            })}
          </div>
        )}

        {/* Custom Preset (Raw JSON Mode) */}
        {attachPreset === "custom" && (
          <>
            <label>
              Payload Type
              <input
                value={customType}
                onChange={(e) => setCustomType(e.target.value)}
              />
            </label>
            <label>
              Content (JSON)
              <textarea
                rows={4}
                value={customContent}
                onChange={(e) => setCustomContent(e.target.value)}
              />
            </label>
            {jsonError && <p className="error hint">{jsonError}</p>}
          </>
        )}

        <button
          disabled={
            attach.isPending ||
            (attachPreset === "custom" && !!jsonError)
          }
          onClick={() => attach.mutate(attachTarget)}
        >
          attach payload
        </button>
      </div>

      <div className="danger-zone">
        <h4>Danger Zone</h4>
        {isDirectlyCut(doc, selection.id, selection.kind) ? (
          <>
            <p>This {selection.kind} is cut. Uncut reinstates it (and any descendants that were only inactive because of this cut).</p>
            <button
              disabled={uncut.isPending}
              onClick={() => uncut.mutate(selection)}
            >
              uncut this {selection.kind}
            </button>
          </>
        ) : (
          <>
            <p>Cutting this unit will make it and its descendants inactive.</p>
            <button
              className="danger"
              disabled={cut.isPending}
              onClick={() => {
                cut.mutate(selection);
                onSelect(null);
              }}
            >
              cut this {selection.kind}
            </button>
          </>
        )}
      </div>
    </section>
  );
}
