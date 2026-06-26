// Detail + action panel for the current selection. Shows payloads, and (in
// live mode) lets you add a step (from a node), attach a payload (to a node or
// step), or cut the selected record.

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

import { artifactSrc } from "./api";
import type { RunClient } from "./api";
import type { LaneEdgeSummary, RunDocument, RunPayload } from "./types";
import type { Selection } from "./Graph";
import {
  isDirectlyCut,
  laneColors,
  laneGroups,
  laneLabel,
  laneOptions,
  nodeLabel,
  payloadsForNode,
  payloadsForStep,
  provenanceFor,
  stepType,
  type LaneOption,
  type LaneColorOverrides,
} from "./model";
import {
  payloadDisplayFor,
  payloadElementFor,
  type PayloadDisplay,
  type PayloadMedia,
  type PayloadSection,
} from "./payloadExtensions";

interface Props {
  doc: RunDocument;
  selection: Selection;
  client: RunClient;
  onSelect: (sel: Selection) => void;
  laneColorOverrides: LaneColorOverrides;
  dark: boolean;
}

interface AttachTarget {
  key: string;
  label: string;
  selection: RecordSelection;
}

interface DetailUnit {
  stepId: string | null;
  outputNodeId: string;
  selected: RecordSelection;
}

type RecordSelection = Extract<Exclude<Selection, null>, { kind: "node" | "step" }>;
type BulkSelection = Extract<Exclude<Selection, null>, { kind: "records" }>;

type AdoptMode = "explicit" | "history" | "reachable" | "lane_head" | "lane_tail";

type Tab = "content" | "flow" | "edit";
type AttachPreset = "note" | "asset" | "git_change" | "diagram" | "command_run" | "custom";

interface FieldDef {
  key: string;
  label: string;
  type: "text" | "number" | "textarea" | "select";
  placeholder?: string;
  defaultValue?: any;
  options?: (doc: RunDocument) => { value: string; label: string }[];
}

interface PayloadSchema {
  type: string;
  label: string;
  fields: FieldDef[];
}

const PAYLOAD_SCHEMAS: Record<string, PayloadSchema> = {
  note: {
    type: "note",
    label: "Note (Markdown)",
    fields: [
      { key: "text", label: "Note Text", type: "textarea", placeholder: "Markdown supported text..." }
    ]
  },
  git_change: {
    type: "git_change",
    label: "Git Change (Git Integration)",
    fields: [
      {
        key: "repo_id",
        label: "Repository",
        type: "select",
        options: (doc) => doc.repos.map((r) => ({ value: r.repo_id, label: r.slug || r.repo_id }))
      },
      { key: "branch", label: "Branch", type: "text", defaultValue: "main" },
      { key: "head_commit", label: "Commit SHA", type: "text", placeholder: "Head commit hash..." }
    ]
  },
  diagram: {
    type: "diagram",
    label: "Diagram (Mermaid / Graphviz)",
    fields: [
      { key: "title", label: "Title", type: "text", placeholder: "Diagram Title" },
      { key: "format", label: "Format", type: "select", options: () => [{ value: "mermaid", label: "Mermaid" }, { value: "graphviz", label: "Graphviz" }] },
      { key: "source", label: "Source Code", type: "textarea", placeholder: "graph TD; A-->B" }
    ]
  },
  command_run: {
    type: "command_run",
    label: "Command Run (Execution Log)",
    fields: [
      { key: "command", label: "Command", type: "text", placeholder: "npm test" },
      { key: "exit_code", label: "Exit Code", type: "number", defaultValue: 0 },
      { key: "cwd", label: "Working Directory (Cwd)", type: "text" },
      { key: "stdout", label: "Stdout", type: "textarea" },
      { key: "stderr", label: "Stderr", type: "textarea" }
    ]
  }
};

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

  // Asset preset state (upload a file as an AssetPayload)
  const [assetFile, setAssetFile] = useState<File | null>(null);

  const [adoptLaneId, setAdoptLaneId] = useState("");
  const [adoptMode, setAdoptMode] = useState<AdoptMode>("explicit");

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
      // Asset is a core payload: upload the file, then attach an AssetPayload
      // to the selected record (not a content-fields payload).
      if (attachPreset === "asset") {
        if (!assetFile) throw new Error("choose a file to attach");
        const info = await client.uploadArtifact(assetFile);
        await client.attachAsset({
          target_id: target.selection.id,
          target_kind: target.selection.kind,
          asset_id: info.artifact_id,
          filename: info.filename,
          mime_type: info.mime_type,
          size_bytes: info.size_bytes,
          path: info.path,
        });
        return;
      }

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
      setAssetFile(null);
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

  const adoptLane = useMutation({
    mutationFn: (unit: DetailUnit) =>
      client.adoptLane(adoptLaneRequest(unit, adoptLaneId, adoptMode)),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: fail,
  });

  const adoptBulkLane = useMutation({
    mutationFn: (sel: BulkSelection) =>
      client.adoptLane({
        lane_id: adoptLaneId,
        record_ids: laneAdoptionRecordIds(sel, doc),
        reason: "web bulk lane adoption",
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: fail,
  });

  // Automatically switch tab depending on whether selection has payloads
  useEffect(() => {
    setAttachTargetKey("step");
    setAdoptMode("explicit");

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

  const lanes = laneOptions(doc);
  useEffect(() => {
    if (!lanes.length) {
      setAdoptLaneId("");
      return;
    }
    if (!lanes.some((lane) => lane.lane_id === adoptLaneId)) {
      const currentLane = lanes.find((lane) => lane.lane_id === doc.current_lane_id);
      setAdoptLaneId(currentLane?.lane_id ?? lanes[0].lane_id ?? "");
    }
  }, [adoptLaneId, doc.current_lane_id, lanes]);

  if (!selection) {
    return (
      <aside className={`panel${isFocused ? " focused" : ""}`} style={{ width: isFocused ? "100%" : panelWidth }}>
        <PanelResizeHandle onPointerDown={startPanelResize} />
        <div className="panel-content">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <p className="muted" style={{ margin: 0 }}>Select a node or step.</p>
            <button 
              type="button" 
              className="panel-focus-btn" 
              title={isFocused ? "Exit Focus Mode" : "Focus Mode"}
              onClick={() => setIsFocused(!isFocused)}
            >
              {isFocused ? (
                <svg viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none">
                  <polyline points="4 14 10 14 10 20" />
                  <polyline points="20 10 14 10 14 4" />
                  <line x1="14" y1="10" x2="21" y2="3" />
                  <line x1="3" y1="21" x2="10" y2="14" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none">
                  <polyline points="15 3 21 3 21 9" />
                  <polyline points="9 21 3 21 3 15" />
                  <line x1="21" y1="3" x2="14" y2="10" />
                  <line x1="3" y1="21" x2="10" y2="14" />
                </svg>
              )}
            </button>
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
        doc={doc}
        selection={selection}
        lanes={lanes}
        adoptLaneId={adoptLaneId}
        setAdoptLaneId={setAdoptLaneId}
        adoptBulkLane={() => adoptBulkLane.mutate(selection)}
        isPending={adoptBulkLane.isPending}
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
          <button 
            type="button" 
            className="panel-focus-btn" 
            title={isFocused ? "Exit Focus Mode" : "Focus Mode"}
            onClick={() => setIsFocused(!isFocused)}
          >
            {isFocused ? (
              <svg viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none">
                <polyline points="4 14 10 14 10 20" />
                <polyline points="20 10 14 10 14 4" />
                <line x1="14" y1="10" x2="21" y2="3" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none">
                <polyline points="15 3 21 3 21 9" />
                <polyline points="9 21 3 21 3 15" />
                <line x1="21" y1="3" x2="14" y2="10" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
            )}
          </button>
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
                <ScopedPayloads client={client} recordId={unit.stepId}>
                  {stepPayloads.map((p) => (
                    <PayloadCard
                      key={p.payload_id}
                      doc={doc}
                      payload={p}
                      display={payloadDisplayFor(p, doc)}
                      onCopyToEdit={p.payload_type === "note" ? handleCopyToEdit : undefined}
                    />
                  ))}
                </ScopedPayloads>

                <h3>output node notes ({nodePayloads.length})</h3>
                {nodePayloads.length === 0 && <p className="muted">none</p>}
                <ScopedPayloads client={client} recordId={unit.outputNodeId}>
                  {nodePayloads.map((p) => (
                    <PayloadCard
                      key={p.payload_id}
                      doc={doc}
                      payload={p}
                      display={payloadDisplayFor(p, doc)}
                      onCopyToEdit={p.payload_type === "note" ? handleCopyToEdit : undefined}
                    />
                  ))}
                </ScopedPayloads>
              </>
            ) : (
              <>
                <h3>node payloads ({nodePayloads.length})</h3>
                {nodePayloads.length === 0 && <p className="muted">none</p>}
                <ScopedPayloads client={client} recordId={unit.outputNodeId}>
                  {nodePayloads.map((p) => (
                    <PayloadCard
                      key={p.payload_id}
                      doc={doc}
                      payload={p}
                      display={payloadDisplayFor(p, doc)}
                      onCopyToEdit={p.payload_type === "note" ? handleCopyToEdit : undefined}
                    />
                  ))}
                </ScopedPayloads>
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
              <h3>adopt into lane</h3>
              {lanes.length === 0 ? (
                <p className="muted">create a lane first</p>
              ) : (
                <>
                  <label>
                    lane
                    <select value={adoptLaneId} onChange={(e) => setAdoptLaneId(e.target.value)}>
                      {lanes.map((lane) => (
                        <option key={lane.group_id} value={lane.lane_id}>
                          {lane.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    scope
                    <select
                      value={adoptMode}
                      onChange={(e) => setAdoptMode(e.target.value as AdoptMode)}
                    >
                      <option value="explicit">{explicitAdoptLabel(unit)}</option>
                      <option value="lane_tail" disabled={!unit.outputNodeId}>
                        selected unit to lane tail
                      </option>
                      <option value="lane_head" disabled={!unit.outputNodeId}>
                        lane head to selected unit
                      </option>
                      <option value="history" disabled={!unit.outputNodeId}>
                        history ending at output node
                      </option>
                      <option value="reachable" disabled={!unit.outputNodeId}>
                        reachable from output node
                      </option>
                    </select>
                  </label>
                  <button
                    disabled={adoptLane.isPending || !adoptLaneId}
                    onClick={() => adoptLane.mutate(unit)}
                  >
                    adopt records
                  </button>
                </>
              )}
            </div>

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
                  <option value="asset">Asset (File)</option>
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

              {/* Asset Preset (upload a file as a core AssetPayload) */}
              {attachPreset === "asset" && (
                <label>
                  File
                  <input
                    type="file"
                    onChange={(e) => setAssetFile(e.target.files?.[0] ?? null)}
                  />
                  <span className="hint muted">
                    Uploads the file into the run and attaches an asset payload to
                    the selected record. It can then be referenced from this record
                    and its descendants.
                  </span>
                </label>
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
                  (attachPreset === "custom" && !!jsonError) ||
                  (attachPreset === "asset" && !assetFile)
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
        )}
      </div>
    </aside>
  );
}

function LaneSummaryPanel({
  doc,
  laneId,
  isFocused,
  panelWidth,
  onFocusToggle,
  onResizeStart,
  onSelect,
  laneColorOverrides,
  dark,
}: {
  doc: RunDocument;
  laneId: string;
  isFocused: boolean;
  panelWidth: number;
  onFocusToggle: () => void;
  onResizeStart: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onSelect: (sel: Selection) => void;
  laneColorOverrides: LaneColorOverrides;
  dark: boolean;
}) {
  const label = laneLabel(doc, laneId);
  const group = laneGroups(doc).find((lane) => lane.lane_id === laneId);
  const summaries = laneEdgeSummariesFor(doc, laneId);
  const edgeNodeIds = new Set(summaries.map((summary) => summary.node_id));
  return (
    <aside className={`panel${isFocused ? " focused" : ""}`} style={{ width: isFocused ? "100%" : panelWidth }}>
      <PanelResizeHandle onPointerDown={onResizeStart} />
      <div className="panel-content">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
          <h2 style={{ margin: 0 }}>
            lane <code>{label}</code>
          </h2>
          <FocusButton focused={isFocused} onClick={onFocusToggle} />
        </div>

        <section
          className="provenance-card"
          style={laneVars(doc, laneId, laneColorOverrides, dark)}
        >
          <h3>lane summary</h3>
          <div className="provenance-row">
            <span>lane</span>
            <strong className="lane-pill">{label}</strong>
          </div>
          <div className="provenance-row">
            <span>records</span>
            <strong>
              {group ? `${group.node_ids.length} nodes · ${group.step_ids.length} steps` : "none"}
            </strong>
          </div>
          <div className="provenance-row">
            <span>summaries</span>
            <strong>{summaries.length}</strong>
          </div>
        </section>

        <section className="panel-view">
          <h3>terminal summaries ({summaries.length})</h3>
          {summaries.length === 0 ? (
            <p className="muted">
              No summaries on active terminal nodes in this lane.
            </p>
          ) : (
            <div className="lane-summary-list">
              {summaries.map((summary) => (
                <LaneSummaryCard
                  key={summary.payload_id}
                  summary={summary}
                  onSelect={onSelect}
                />
              ))}
            </div>
          )}
        </section>

        <section className="record-context">
          <h3>terminal nodes</h3>
          {edgeNodeIds.size === 0 ? (
            <p className="muted">No summarized terminal nodes.</p>
          ) : (
            <div className="flow-list">
              {[...edgeNodeIds].map((nodeId) => (
                <button
                  key={nodeId}
                  type="button"
                  className="unit-card"
                  onClick={() => onSelect({ kind: "node", id: nodeId })}
                >
                  <span className="unit-card-title">{nodeLabel(doc, nodeId)}</span>
                  <span className="unit-card-ids">
                    <code>n:{nodeId.slice(0, 8)}</code>
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </aside>
  );
}

function LaneSummaryCard({
  summary,
  onSelect,
}: {
  summary: LaneEdgeSummary;
  onSelect: (sel: Selection) => void;
}) {
  return (
    <article className="lane-summary-card">
      <div className="payload-card-head">
        <strong>node summary</strong>
        <button
          type="button"
          className="summary-node-link"
          onClick={() => onSelect({ kind: "node", id: summary.node_id })}
        >
          {summary.node_id.slice(0, 12)}
        </button>
      </div>
      <div className="payload-markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
          {summary.text || "(summary)"}
        </ReactMarkdown>
      </div>
      <div className="unit-card-ids">
        <code>payload:{summary.payload_id.slice(0, 8)}</code>
      </div>
    </article>
  );
}

function laneEdgeSummariesFor(doc: RunDocument, laneId: string): LaneEdgeSummary[] {
  return (doc.lane_edge_summaries ?? []).filter((summary) => summary.lane_id === laneId);
}

function FocusButton({
  focused,
  onClick,
}: {
  focused: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="panel-focus-btn"
      title={focused ? "Exit Focus Mode" : "Focus Mode"}
      onClick={onClick}
    >
      {focused ? (
        <svg viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none">
          <polyline points="4 14 10 14 10 20" />
          <polyline points="20 10 14 10 14 4" />
          <line x1="14" y1="10" x2="21" y2="3" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none">
          <polyline points="15 3 21 3 21 9" />
          <polyline points="9 21 3 21 3 15" />
          <line x1="21" y1="3" x2="14" y2="10" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
      )}
    </button>
  );
}

function ProvenanceCard({
  doc,
  unit,
  laneColorOverrides,
  dark,
}: {
  doc: RunDocument;
  unit: DetailUnit;
  laneColorOverrides: LaneColorOverrides;
  dark: boolean;
}) {
  const primaryId = unit.stepId ?? unit.outputNodeId;
  const primaryKind = unit.stepId ? "step" : "node";
  const provenance =
    provenanceFor(doc, primaryId) ??
    (unit.outputNodeId ? provenanceFor(doc, unit.outputNodeId) : null);

  if (!provenance) {
    return (
      <section className="provenance-card missing">
        <h3>provenance</h3>
        <div className="provenance-row">
          <span>lane</span>
          <strong>none recorded</strong>
        </div>
        <p className="muted">
          This record has no lane provenance. It may have been created before lane
          attribution was recorded, or without a work session.
        </p>
      </section>
    );
  }

  const lane = provenance.lane_name || laneLabel(doc, provenance.lane_id);
  const actorLabel = provenance.membership_kind === "adopted" ? "adopted by" : "created by";
  return (
    <section className="provenance-card" style={laneVars(doc, provenance.lane_id, laneColorOverrides, dark)}>
      <h3>provenance</h3>
      <div className="provenance-row">
        <span>lane</span>
        <strong className="lane-pill">{lane}</strong>
      </div>
      <div className="provenance-row">
        <span>record</span>
        <code>{primaryKind}:{primaryId.slice(0, 12)}</code>
      </div>
      <div className="provenance-row">
        <span>{actorLabel}</span>
        <strong>{provenance.user_id}</strong>
      </div>
      <div className="provenance-row">
        <span>event</span>
        <code>{provenance.event_type}</code>
      </div>
      {provenance.created_at && (
        <div className="provenance-row">
          <span>created at</span>
          <time>{provenance.created_at}</time>
        </div>
      )}
    </section>
  );
}

function laneVars(
  doc: RunDocument,
  laneId: string,
  laneColorOverrides: LaneColorOverrides,
  dark: boolean,
): CSSProperties {
  const colors = laneColors(doc, laneId, laneColorOverrides, dark);
  return {
    "--lane-color": colors.laneColor,
    "--lane-bg": colors.laneBg,
  } as CSSProperties;
}

function parseJson(raw: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("content must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

function adoptLaneRequest(unit: DetailUnit, laneId: string, mode: AdoptMode) {
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

function explicitAdoptRecordIds(unit: DetailUnit): string[] {
  if (unit.stepId) {
    return [unit.stepId, unit.outputNodeId].filter(Boolean);
  }
  return [unit.outputNodeId];
}

function explicitAdoptLabel(unit: DetailUnit): string {
  return unit.stepId ? "selected unit (step + output)" : "selected node only";
}

function selectedRecordIds(selection: BulkSelection): string[] {
  return [...new Set(selection.records.map((record) => record.id))];
}

function laneAdoptionRecordIds(selection: BulkSelection, doc: RunDocument): string[] {
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

function visibleRecordIds(ids: string[]): string[] {
  return ids.slice(0, 24);
}

function BulkRecordsPanel({
  doc,
  selection,
  lanes,
  adoptLaneId,
  setAdoptLaneId,
  adoptBulkLane,
  isPending,
  error,
  isFocused,
  panelWidth,
  onFocusToggle,
  onResizeStart,
}: {
  doc: RunDocument;
  selection: BulkSelection;
  lanes: LaneOption[];
  adoptLaneId: string;
  setAdoptLaneId: (id: string) => void;
  adoptBulkLane: () => void;
  isPending: boolean;
  error: string | null;
  isFocused: boolean;
  panelWidth: number;
  onFocusToggle: () => void;
  onResizeStart: (event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  const [activeTab, setActiveTab] = useState<"selection" | "edit">("selection");
  const recordIds = selectedRecordIds(selection);
  const adoptionRecordIds = laneAdoptionRecordIds(selection, doc);
  const previewRecordIds = visibleRecordIds(recordIds);
  const hiddenRecordCount = recordIds.length - previewRecordIds.length;
  const nodeCount = selection.records.filter((record) => record.kind === "node").length;
  const stepCount = selection.records.filter((record) => record.kind === "step").length;

  return (
    <aside className={`panel${isFocused ? " focused" : ""}`} style={{ width: isFocused ? "100%" : panelWidth }}>
      <PanelResizeHandle onPointerDown={onResizeStart} />
      <div className="panel-content">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
          <h2 style={{ margin: 0 }}>
            multiple records <code>{recordIds.length}</code>
          </h2>
          <button
            type="button"
            className="panel-focus-btn"
            title={isFocused ? "Exit Focus Mode" : "Focus Mode"}
            onClick={onFocusToggle}
          >
            {isFocused ? (
              <svg viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none">
                <polyline points="4 14 10 14 10 20" />
                <polyline points="20 10 14 10 14 4" />
                <line x1="14" y1="10" x2="21" y2="3" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none">
                <polyline points="15 3 21 3 21 9" />
                <polyline points="9 21 3 21 3 15" />
                <line x1="21" y1="3" x2="14" y2="10" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
            )}
          </button>
        </div>
        {error && <div className="error">{error}</div>}

        <div className="panel-tabs">
          <button
            type="button"
            className={`panel-tab-btn${activeTab === "selection" ? " active" : ""}`}
            onClick={() => setActiveTab("selection")}
          >
            Selection
          </button>
          <button
            type="button"
            className={`panel-tab-btn${activeTab === "edit" ? " active" : ""}`}
            onClick={() => setActiveTab("edit")}
          >
            Edit
          </button>
        </div>

        {activeTab === "selection" && (
          <section className="panel-view">
            <div className="edit-section">
              <h3>overview</h3>
              <p className="muted" style={{ marginTop: 0 }}>
                {nodeCount} nodes · {stepCount} steps
              </p>
            </div>
            <div className="edit-section">
              <h3>record ids ({recordIds.length})</h3>
              <div className="record-id-list">
                {previewRecordIds.map((id) => (
                  <code key={id} className="record-id-chip">
                    {id}
                  </code>
                ))}
              </div>
              {hiddenRecordCount > 0 && (
                <p className="muted" style={{ marginBottom: 0 }}>
                  and {hiddenRecordCount} more selected records
                </p>
              )}
            </div>
          </section>
        )}

        {activeTab === "edit" && (
          <section className="actions panel-edit-tabs">
            <div className="edit-section">
              <h3>move selection into lane</h3>
              <p className="muted">
                Moves the selected records. Related producer/output records are included when needed for lane consistency.
              </p>
              {lanes.length === 0 ? (
                <p className="muted">create a lane first</p>
              ) : (
                <>
                  <label>
                    lane
                    <select value={adoptLaneId} onChange={(e) => setAdoptLaneId(e.target.value)}>
                      {lanes.map((lane) => (
                        <option key={lane.group_id} value={lane.lane_id}>
                          {lane.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button disabled={isPending || !adoptLaneId || adoptionRecordIds.length === 0} onClick={adoptBulkLane}>
                    move {adoptionRecordIds.length} records
                  </button>
                </>
              )}
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}

function useResizablePanelWidth(): [
  number,
  (event: ReactPointerEvent<HTMLDivElement>) => void,
] {
  const [width, setWidth] = useState(() => {
    const raw = window.localStorage.getItem("arctx.panelWidth");
    const saved = raw ? Number(raw) : NaN;
    return Number.isFinite(saved) ? clampPanelWidth(saved) : 420;
  });

  useEffect(() => {
    window.localStorage.setItem("arctx.panelWidth", String(width));
  }, [width]);

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    document.body.classList.add("resizing-panel");

    const onMove = (moveEvent: PointerEvent) => {
      setWidth(clampPanelWidth(startWidth + startX - moveEvent.clientX));
    };
    const onUp = () => {
      document.body.classList.remove("resizing-panel");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  };

  return [width, startResize];
}

function clampPanelWidth(width: number): number {
  const max = Math.max(360, window.innerWidth - 280);
  return Math.min(Math.max(width, 300), Math.min(900, max));
}

function PanelResizeHandle({
  onPointerDown,
}: {
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      className="panel-resize-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize detail panel"
      onPointerDown={onPointerDown}
    />
  );
}

function detailUnitFor(doc: RunDocument, selection: RecordSelection): DetailUnit {
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

function attachTargetsFor(unit: DetailUnit): AttachTarget[] {
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

function SelectionContext({
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

function PayloadCard({
  doc,
  payload,
  display,
  onCopyToEdit,
}: {
  doc: RunDocument;
  payload: RunPayload;
  display: PayloadDisplay;
  onCopyToEdit?: (text: string) => void;
}) {
  const element = payloadElementFor(payload);
  return (
    <section className={`payload-card${display.raw ? " raw" : ""}`}>
      <div className="payload-card-head">
        <strong>{display.title}</strong>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {payload.payload_type === "asset" && (
            <button
              type="button"
              className="payload-copy-btn"
              title="copy a markdown reference (paste into a note on this record or a descendant)"
              onClick={() => {
                const url = `/${String(payload.path ?? "").replace(/^\/+/, "")}`;
                const name = String(payload.filename ?? "asset");
                const md = String(payload.mime_type ?? "").startsWith("image/")
                  ? `![${name}](${url})`
                  : `[${name}](${url})`;
                void navigator.clipboard?.writeText(md);
              }}
            >
              copy md
            </button>
          )}
          {onCopyToEdit && (
            <button
              type="button"
              className="payload-copy-btn"
              onClick={() => {
                const text = typeof payload.content?.text === "string" ? payload.content.text : "";
                onCopyToEdit(text);
              }}
            >
              Copy to Edit
            </button>
          )}
          <code>{payload.payload_id.slice(0, 12)}</code>
        </div>
      </div>
      {display.summary && <p className="payload-summary">{display.summary}</p>}
      {display.media?.map((media, index) => (
        <PayloadMediaView key={`${media.src}:${index}`} media={media} />
      ))}
      {display.fields && display.fields.length > 0 && (
        <dl className="payload-fields">
          {display.fields.map((field) => (
            <div key={field.label}>
              <dt>{field.label}</dt>
              <dd>{formatValue(field.value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {element && (
        <PayloadCustomElement
          tagName={element.tagName}
          doc={doc}
          payload={payload}
          display={display}
        />
      )}
      {display.sections?.map((section, index) => (
        <PayloadSectionView key={`${section.title}:${index}`} section={section} />
      ))}
      {!display.raw && (
        <details className="payload-raw">
          <summary>raw JSON</summary>
          <pre className="payload">{JSON.stringify(payload, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}

function PayloadSectionView({ section }: { section: PayloadSection }) {
  const body = (
    <div className="payload-section">
      <h4>{section.title}</h4>
      <PayloadSectionBody section={section} />
    </div>
  );
  if (!section.collapsed) return body;
  return (
    <details className="payload-section-details">
      <summary>{section.title}</summary>
      <PayloadSectionBody section={section} />
    </details>
  );
}

function PayloadSectionBody({ section }: { section: PayloadSection }) {
  if (section.kind === "image") {
    return <PayloadMediaView media={mediaFromSection(section)} />;
  }
  if (section.kind === "markdown") {
    return <MarkdownView value={section.value} />;
  }
  if (section.kind === "text" || section.kind === "diff") {
    return (
      <pre className={`payload payload-text${section.kind === "diff" ? " payload-diff" : ""}`}>
        {formatValue(section.value)}
      </pre>
    );
  }
  if (section.kind === "table") {
    return <PayloadTable value={section.value} />;
  }
  return <pre className="payload">{JSON.stringify(section.value, null, 2)}</pre>;
}

// Set of artifact URLs (e.g. "/artifacts/ast_xxx_file.png") that may be
// referenced from the record currently being rendered. `null` means no
// scoping (static/share mode, or still loading) — render everything.
const ArtifactScopeContext = createContext<Set<string> | null>(null);

function artifactKey(src: string): string {
  let s = src;
  if (s.startsWith("artifact://")) s = `/artifacts/${s.slice("artifact://".length).replace(/^\/+/, "")}`;
  try {
    return decodeURI(s);
  } catch {
    return s;
  }
}

function isArtifactUrl(src: string): boolean {
  return src.startsWith("/artifacts/") || src.startsWith("artifact://");
}

// Wraps a record's payload cards, providing the set of assets visible from
// that record so embedded artifact URLs out of scope (descendants/unrelated)
// are not rendered. Live mode only; static shares render everything.
function ScopedPayloads({
  client,
  recordId,
  children,
}: {
  client: RunClient;
  recordId: string;
  children: ReactNode;
}) {
  const { data } = useQuery({
    queryKey: ["visibleAssets", recordId],
    queryFn: () => client.visibleAssets(recordId),
    enabled: client.writable && !!recordId,
  });
  const scope = useMemo(() => {
    if (!client.writable || !data) return null;
    const set = new Set<string>();
    for (const a of data) {
      const path = String((a as { path?: unknown }).path ?? "").replace(/^\/+/, "");
      if (path) set.add(artifactKey(`/${path}`));
    }
    return set;
  }, [client.writable, data]);
  return <ArtifactScopeContext.Provider value={scope}>{children}</ArtifactScopeContext.Provider>;
}

function MarkdownView({ value }: { value: unknown }) {
  return (
    <div className="payload-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{ img: ScopedMarkdownImg }}
      >
        {formatValue(value)}
      </ReactMarkdown>
    </div>
  );
}

function ScopedMarkdownImg({ src, alt }: { src?: string; alt?: string }) {
  const scope = useContext(ArtifactScopeContext);
  const raw = typeof src === "string" ? src : "";
  if (isArtifactUrl(raw) && scope && !scope.has(artifactKey(raw))) {
    return <span className="muted payload-media-blocked">⚠ asset not in scope</span>;
  }
  const safe = isArtifactUrl(raw) ? safeImageSrc(raw) : raw;
  if (!safe) {
    return <span className="muted payload-media-blocked">blocked image source</span>;
  }
  return <img src={safe} alt={alt ?? ""} loading="lazy" />;
}

function PayloadMediaView({ media }: { media: PayloadMedia }) {
  const src = safeImageSrc(media.src);
  if (!src) {
    return <p className="muted payload-media-blocked">blocked image source</p>;
  }
  return (
    <figure className="payload-media">
      <img src={src} alt={media.alt ?? ""} loading="lazy" />
      {media.caption && <figcaption>{media.caption}</figcaption>}
    </figure>
  );
}

function PayloadTable({ value }: { value: unknown }) {
  const table = tableData(value);
  if (!table) {
    return <pre className="payload">{JSON.stringify(value, null, 2)}</pre>;
  }
  return (
    <div className="payload-table-wrap">
      <table className="payload-table">
        <thead>
          <tr>
            {table.columns.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, index) => (
            <tr key={index}>
              {table.columns.map((col) => (
                <td key={col}>{formatValue(row[col])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PayloadCustomElement({
  tagName,
  doc,
  payload,
  display,
}: {
  tagName: string;
  doc: RunDocument;
  payload: RunPayload;
  display: PayloadDisplay;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    host.replaceChildren();
    const element = document.createElement(tagName) as HTMLElement & {
      doc?: RunDocument;
      payload?: RunPayload;
      display?: PayloadDisplay;
    };
    element.doc = doc;
    element.payload = payload;
    element.display = display;
    host.appendChild(element);
    return () => host.replaceChildren();
  }, [tagName, doc, payload, display]);
  return <div className="payload-custom-element-host" ref={ref} />;
}

function mediaFromSection(section: PayloadSection): PayloadMedia {
  if (typeof section.value === "string") {
    return { kind: "image", src: section.value, alt: section.title };
  }
  if (typeof section.value === "object" && section.value !== null && !Array.isArray(section.value)) {
    const raw = section.value as Record<string, unknown>;
    return {
      kind: "image",
      src: typeof raw.src === "string" ? raw.src : "",
      alt: typeof raw.alt === "string" ? raw.alt : section.title,
      caption: typeof raw.caption === "string" ? raw.caption : undefined,
    };
  }
  return { kind: "image", src: "", alt: section.title };
}

function safeImageSrc(src: string): string | null {
  if (src.length > 7_000_000) return null;
  if (/^data:image\/(png|jpeg|webp);base64,[a-z0-9+/=\s]+$/i.test(src)) {
    return src;
  }
  if (src.startsWith("artifact://")) {
    const path = src.slice("artifact://".length).replace(/^\/+/, "");
    return artifactPath(path);
  }
  if (src.startsWith("/artifacts/")) {
    return artifactPath(src.slice("/artifacts/".length));
  }
  return null;
}

function artifactPath(path: string): string | null {
  const parts = path.split("/").filter(Boolean);
  if (!parts.length || parts.some((part) => part === "." || part === "..")) return null;
  // artifactSrc appends ?run= when the picker has switched runs, so the file
  // resolves against the selected run rather than the server's bound run.
  return artifactSrc(`/artifacts/${parts.map(encodeURIComponent).join("/")}`);
}

function tableData(value: unknown): { columns: string[]; rows: Record<string, unknown>[] } | null {
  if (Array.isArray(value)) {
    const rows = value
      .filter((row) => typeof row === "object" && row !== null && !Array.isArray(row))
      .map((row) => row as Record<string, unknown>);
    if (!rows.length) return null;
    const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
    return { columns, rows };
  }
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    const raw = value as Record<string, unknown>;
    const rawColumns = Array.isArray(raw.columns) ? raw.columns.map(String) : [];
    const rawRows = Array.isArray(raw.rows) ? raw.rows : [];
    const rows = rawRows.map((row) => {
      if (Array.isArray(row)) {
        return Object.fromEntries(rawColumns.map((col, index) => [col, row[index]]));
      }
      return typeof row === "object" && row !== null ? (row as Record<string, unknown>) : {};
    });
    const columns = rawColumns.length
      ? rawColumns
      : Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
    return columns.length && rows.length ? { columns, rows } : null;
  }
  return null;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
