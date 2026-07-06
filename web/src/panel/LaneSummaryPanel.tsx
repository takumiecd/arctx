// Detail panel shown when a lane (collapsed-lane card, or lane menu entry) is
// selected: lane metadata plus its terminal-node summaries.

import type { PointerEvent as ReactPointerEvent } from "react";

import type { Selection } from "../Graph";
import {
  laneById,
  laneGroups,
  laneLabel,
  laneStatus,
  nodeLabel,
  type LaneColorOverrides,
} from "../model";
import type { LaneEdgeSummary, RunDocument } from "../types";
import { FocusButton } from "./FocusButton";
import { laneVars } from "./ProvenanceCard";
import { PanelResizeHandle } from "./resize";
import { SummaryBody, summaryFormat } from "./markdown";

export function LaneSummaryPanel({
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
  const lane = laneById(doc, laneId);
  const status = laneStatus(doc, laneId);
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
            <span>status</span>
            <strong className={`lane-status-badge ${status}`}>{status}</strong>
          </div>
          {status === "closed" && lane?.closed_at && (
            <div className="provenance-row">
              <span>closed</span>
              <time>{lane.closed_at}</time>
            </div>
          )}
          <div className="provenance-row">
            <span>opened by</span>
            <strong>{lane?.created_by ?? "unknown"}</strong>
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
      <SummaryBody text={summary.text || "(summary)"} format={summaryFormat(summary.metadata?.format)} />
      <div className="unit-card-ids">
        <code>payload:{summary.payload_id.slice(0, 8)}</code>
      </div>
    </article>
  );
}

function laneEdgeSummariesFor(doc: RunDocument, laneId: string): LaneEdgeSummary[] {
  return (doc.lane_edge_summaries ?? []).filter((summary) => summary.lane_id === laneId);
}
