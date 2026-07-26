// Detail + action panel for the current selection. Shows payloads, and (in
// live mode) lets you add a step (from a node), attach a payload (to a node or
// step), or cut the selected record.

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  payloadsForNode,
  payloadsForStep,
} from "./model";
import { payloadDisplayFor } from "./payloadExtensions";
import { BulkRecordsPanel } from "./panel/BulkRecordsPanel";
import { FocusButton } from "./panel/FocusButton";
import { LaneSummaryPanel } from "./panel/LaneSummaryPanel";
import { PayloadCard } from "./panel/PayloadCard";
import { ProvenanceCard } from "./panel/ProvenanceCard";
import { SelectionContext } from "./panel/SelectionContext";
import {
  attachTargetsFor,
  detailUnitFor,
  parseJson,
} from "./panel/helpers";
import { RecordEditForm } from "./panel/RecordEditForm";
import { PanelResizeHandle, useResizablePanelWidth } from "./panel/resize";
import { PAYLOAD_SCHEMAS } from "./panel/schemas";
import type {
  AttachPreset,
  AttachTarget,
  Props,
  RecordSelection,
  Tab,
} from "./panel/types";

export function Panel({ doc, selection, client, onSelect, laneColorOverrides, dark }: Props) {
  const qc = useQueryClient();
  const [panelWidth, startPanelResize] = useResizablePanelWidth();
  const [activeTab, setActiveTab] = useState<Tab>("content");
  const [isFocused, setIsFocused] = useState(false);

  // Step state
  const [stepType, setStepType] = useState("experiment");
  const [stepRawJsonMode, setStepRawJsonMode] = useState(false);
  const [stepNoteText, setStepNoteText] = useState("");
  const [stepContent, setStepContent] = useState("{}");
  const [stepJsonError, setStepJsonError] = useState<string | null>(null);

  // Reparent state (comma-separated new input node ids)
  const [reparentInputs, setReparentInputs] = useState("");

  // Attach state
  const [attachPreset, setAttachPreset] = useState<AttachPreset>("note");
  const [attachTargetKey, setAttachTargetKey] = useState("step");

  // Form values state for schema-driven dynamic fields
  const [formValues, setFormValues] = useState<Record<string, any>>({});

  // Custom preset states
  const [customType, setCustomType] = useState("custom_data");
  const [customContent, setCustomContent] = useState("{}");

  const [jsonError, setJsonError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["run"] });
  const fail = (e: Error) => setError(e.message);

  // Populate dynamic form defaults based on current preset and document repos
  useEffect(() => {
    const schema = PAYLOAD_SCHEMAS[attachPreset];
    if (!schema) return;
    const initialValues: Record<string, any> = {};
    for (const f of schema.fields) {
      if (f.type === "select" && f.options) {
        const opts = f.options(doc);
        initialValues[f.key] = formValues[f.key] ?? opts[0]?.value ?? "";
      } else {
        initialValues[f.key] = formValues[f.key] ?? f.defaultValue ?? "";
      }
    }
    setFormValues((prev) => ({ ...prev, ...initialValues }));
  }, [attachPreset, doc]);

  const addStep = useMutation({
    mutationFn: (nodeId: string) => {
      let contentObj: Record<string, unknown> = {};
      if (stepRawJsonMode) {
        contentObj = parseJson(stepContent);
      } else {
        contentObj = stepNoteText ? { text: stepNoteText } : {};
      }
      return client.addStep({
        input_node_ids: [nodeId],
        type: stepType,
        content: contentObj,
      });
    },
    onSuccess: () => {
      setError(null);
      setStepNoteText("");
      setStepContent("{}");
      invalidate();
    },
    onError: fail,
  });

  const attach = useMutation({
    mutationFn: async (target: AttachTarget) => {
      let typeVal = "";
      let contentObj: Record<string, unknown> = {};

      if (attachPreset === "custom") {
        typeVal = customType;
        contentObj = parseJson(customContent);
      } else {
        const schema = PAYLOAD_SCHEMAS[attachPreset];
        typeVal = schema.type;
        // Build payload content filtering to match schema keys
        const filtered: Record<string, unknown> = {};
        for (const f of schema.fields) {
          filtered[f.key] = formValues[f.key] ?? f.defaultValue ?? "";
        }
        contentObj = filtered;
      }

      return client.attach({
        target_id: target.selection.id,
        target_kind: target.selection.kind,
        type: typeVal,
        content: contentObj,
      });
    },
    onSuccess: () => {
      setError(null);
      // Reset preset fields
      setFormValues({});
      setCustomContent("{}");
      invalidate();
    },
    onError: fail,
  });

  const cut = useMutation({
    mutationFn: (sel: RecordSelection) =>
      client.cut({ target_id: sel.id, target_kind: sel.kind }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: fail,
  });

  const uncut = useMutation({
    mutationFn: (sel: RecordSelection) =>
      client.uncut({ target_id: sel.id, target_kind: sel.kind }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: fail,
  });

  const reparent = useMutation({
    mutationFn: (vars: { nodeId: string; inputs: string[]; type: string }) =>
      client.reparent({
        node_id: vars.nodeId,
        input_node_ids: vars.inputs,
        type: vars.type || "reparent",
      }),
    onSuccess: () => {
      setError(null);
      setReparentInputs("");
      invalidate();
    },
    onError: fail,
  });

  // Automatically switch tab depending on whether selection has payloads
  useEffect(() => {
    setAttachTargetKey("step");

    if (selection?.kind === "lane") {
      setActiveTab("content");
    } else if (selection?.kind === "records") {
      setActiveTab("edit");
    } else if (selection) {
      const unit = detailUnitFor(doc, selection);
      const stepPayloads = unit.stepId ? payloadsForStep(doc, unit.stepId) : [];
      const nodePayloads = payloadsForNode(doc, unit.outputNodeId);
      const hasPayloads = stepPayloads.length > 0 || nodePayloads.length > 0;
      setActiveTab(hasPayloads ? "content" : "flow");
    }
  }, [selection]);

  const handleCopyToEdit = (text: string) => {
    setAttachPreset("note");
    setFormValues((prev) => ({ ...prev, text }));
    setActiveTab("edit");
    setAttachTargetKey("step");
  };

  // Real-time JSON validation for customContent
  useEffect(() => {
    if (attachPreset !== "custom") {
      setJsonError(null);
      return;
    }
    const trimmed = customContent.trim();
    if (!trimmed) {
      setJsonError(null);
      return;
    }
    try {
      const parsed = JSON.parse(trimmed);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setJsonError("JSON must be an object");
      } else {
        setJsonError(null);
      }
    } catch (e) {
      setJsonError((e as Error).message);
    }
  }, [customContent, attachPreset]);

  // Real-time JSON validation for stepContent
  useEffect(() => {
    if (!stepRawJsonMode) {
      setStepJsonError(null);
      return;
    }
    const trimmed = stepContent.trim();
    if (!trimmed) {
      setStepJsonError(null);
      return;
    }
    try {
      const parsed = JSON.parse(trimmed);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setStepJsonError("JSON must be an object");
      } else {
        setStepJsonError(null);
      }
    } catch (e) {
      setStepJsonError((e as Error).message);
    }
  }, [stepContent, stepRawJsonMode]);


  if (!selection) {
    return (
      <aside className={`panel${isFocused ? " focused" : ""}`} style={{ width: isFocused ? "100%" : panelWidth }}>
        <PanelResizeHandle onPointerDown={startPanelResize} />
        <div className="panel-content">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <p className="muted" style={{ margin: 0 }}>Select a node or step.</p>
            <FocusButton focused={isFocused} onClick={() => setIsFocused(!isFocused)} />
          </div>
        </div>
      </aside>
    );
  }

  if (selection.kind === "lane") {
    return (
      <LaneSummaryPanel
        doc={doc}
        laneId={selection.id}
        isFocused={isFocused}
        panelWidth={panelWidth}
        onFocusToggle={() => setIsFocused(!isFocused)}
        onResizeStart={startPanelResize}
        onSelect={onSelect}
        laneColorOverrides={laneColorOverrides}
        dark={dark}
      />
    );
  }

  if (selection.kind === "records") {
    return (
      <BulkRecordsPanel
        selection={selection}
        error={error}
        isFocused={isFocused}
        panelWidth={panelWidth}
        onFocusToggle={() => setIsFocused(!isFocused)}
        onResizeStart={startPanelResize}
      />
    );
  }

  const unit = detailUnitFor(doc, selection);
  const stepPayloads = unit.stepId ? payloadsForStep(doc, unit.stepId) : [];
  const nodePayloads = payloadsForNode(doc, unit.outputNodeId);
  const attachTargets = attachTargetsFor(unit);
  const attachTarget = attachTargets.find((target) => target.key === attachTargetKey) ?? attachTargets[0];

  return (
    <aside className={`panel${isFocused ? " focused" : ""}`} style={{ width: isFocused ? "100%" : panelWidth }}>
      <PanelResizeHandle onPointerDown={startPanelResize} />
      <div className="panel-content">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
          <h2 style={{ margin: 0 }}>
            {unit.stepId ? "step + output" : "node"}{" "}
            <code>{(unit.stepId ?? unit.outputNodeId).slice(0, 12)}</code>
          </h2>
          <FocusButton focused={isFocused} onClick={() => setIsFocused(!isFocused)} />
        </div>

        {client.writable ? (
          <div className="panel-tabs">
            <button
              type="button"
              className={`panel-tab-btn${activeTab === "content" ? " active" : ""}`}
              onClick={() => setActiveTab("content")}
            >
              Content
            </button>
            <button
              type="button"
              className={`panel-tab-btn${activeTab === "flow" ? " active" : ""}`}
              onClick={() => setActiveTab("flow")}
            >
              Flow
            </button>
            <button
              type="button"
              className={`panel-tab-btn${activeTab === "edit" ? " active" : ""}`}
              onClick={() => setActiveTab("edit")}
            >
              Edit
            </button>
          </div>
        ) : (
          <div className="panel-tabs">
            <button
              type="button"
              className={`panel-tab-btn${activeTab === "content" ? " active" : ""}`}
              onClick={() => setActiveTab("content")}
            >
              Content
            </button>
            <button
              type="button"
              className={`panel-tab-btn${activeTab === "flow" ? " active" : ""}`}
              onClick={() => setActiveTab("flow")}
            >
              Flow
            </button>
          </div>
        )}

        {activeTab === "content" && (
          <section className="panel-view">
            {unit.stepId ? (
              <>
                <h3>step payloads ({stepPayloads.length})</h3>
                {stepPayloads.length === 0 && <p className="muted">none</p>}
                {stepPayloads.map((p) => (
                  <PayloadCard
                    key={p.payload_id}
                    doc={doc}
                    payload={p}
                    display={payloadDisplayFor(p, doc)}
                    client={client}
                    onCopyToEdit={p.payload_type === "note" ? handleCopyToEdit : undefined}
                  />
                ))}

                <h3>output node notes ({nodePayloads.length})</h3>
                {nodePayloads.length === 0 && <p className="muted">none</p>}
                {nodePayloads.map((p) => (
                  <PayloadCard
                    key={p.payload_id}
                    doc={doc}
                    payload={p}
                    display={payloadDisplayFor(p, doc)}
                    client={client}
                    onCopyToEdit={p.payload_type === "note" ? handleCopyToEdit : undefined}
                  />
                ))}
              </>
            ) : (
              <>
                <h3>node payloads ({nodePayloads.length})</h3>
                {nodePayloads.length === 0 && <p className="muted">none</p>}
                {nodePayloads.map((p) => (
                  <PayloadCard
                    key={p.payload_id}
                    doc={doc}
                    payload={p}
                    display={payloadDisplayFor(p, doc)}
                    client={client}
                    onCopyToEdit={p.payload_type === "note" ? handleCopyToEdit : undefined}
                  />
                ))}
              </>
            )}
          </section>
        )}

        {activeTab === "flow" && (
          <section className="panel-view">
            <ProvenanceCard doc={doc} unit={unit} laneColorOverrides={laneColorOverrides} dark={dark} />
            <SelectionContext doc={doc} unit={unit} onSelect={onSelect} />
          </section>
        )}

        {activeTab === "edit" && client.writable && (
          <RecordEditForm
            doc={doc}
            unit={unit}
            selection={selection}
            error={error}
            stepType={stepType}
            setStepType={setStepType}
            stepRawJsonMode={stepRawJsonMode}
            setStepRawJsonMode={setStepRawJsonMode}
            stepContent={stepContent}
            setStepContent={setStepContent}
            stepNoteText={stepNoteText}
            setStepNoteText={setStepNoteText}
            stepJsonError={stepJsonError}
            addStep={addStep}
            reparentInputs={reparentInputs}
            setReparentInputs={setReparentInputs}
            reparent={reparent}
                    attachTargets={attachTargets}
            attachTarget={attachTarget}
            setAttachTargetKey={setAttachTargetKey}
            attachPreset={attachPreset}
            setAttachPreset={setAttachPreset}
            formValues={formValues}
            setFormValues={setFormValues}
            customType={customType}
            setCustomType={setCustomType}
            customContent={customContent}
            setCustomContent={setCustomContent}
            jsonError={jsonError}
            attach={attach}
            uncut={uncut}
            cut={cut}
            onSelect={onSelect}
          />
        )}
      </div>
    </aside>
  );
}
