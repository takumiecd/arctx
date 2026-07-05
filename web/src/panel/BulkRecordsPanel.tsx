// Detail panel shown when multiple nodes/steps are shift-selected: an
// overview of the selection plus a bulk "move into lane" action.

import { useState, type PointerEvent as ReactPointerEvent } from "react";

import type { LaneOption } from "../model";
import type { RunDocument } from "../types";
import { FocusButton } from "./FocusButton";
import { laneAdoptionRecordIds, selectedRecordIds, visibleRecordIds } from "./helpers";
import { PanelResizeHandle } from "./resize";
import type { BulkSelection } from "./types";

export function BulkRecordsPanel({
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
          <FocusButton focused={isFocused} onClick={onFocusToggle} />
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
