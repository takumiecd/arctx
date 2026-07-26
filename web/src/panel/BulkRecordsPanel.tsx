// Detail panel shown when multiple nodes/steps are shift-selected: an
// overview of the selection.

import type { PointerEvent as ReactPointerEvent } from "react";

import { FocusButton } from "./FocusButton";
import { selectedRecordIds, visibleRecordIds } from "./helpers";
import { PanelResizeHandle } from "./resize";
import type { BulkSelection } from "./types";

export function BulkRecordsPanel({
  selection,
  error,
  isFocused,
  panelWidth,
  onFocusToggle,
  onResizeStart,
}: {
  selection: BulkSelection;
  error: string | null;
  isFocused: boolean;
  panelWidth: number;
  onFocusToggle: () => void;
  onResizeStart: (event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  const recordIds = selectedRecordIds(selection);
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
      </div>
    </aside>
  );
}
