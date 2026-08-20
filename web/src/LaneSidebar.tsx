// Flat lane sidebar + client-side search — the web mirror of `arctx explore`.
//
// Lanes are flat work units, so this is a list, not a tree: open lanes first
// with their one-line current summary, closed lanes folded behind a toggle.
// The search box is `explore --query`: case-insensitive AND over lane names,
// lane purposes, and the payloads each lane owns, all from the loaded
// document.

import { useMemo, useState, type CSSProperties } from "react";

import { collapseSummary, hitTargets, laneOverviews, searchLanes } from "./lanes";
import { laneColors, type LaneColorOverrides } from "./model";
import type { RunDocument } from "./types";
import type { Selection } from "./Graph";

export function LaneSidebar({
  doc,
  activeLaneId,
  selection,
  laneColorOverrides,
  dark,
  onSelectLane,
  onSelectRecord,
}: {
  doc: RunDocument;
  activeLaneId: string | null;
  selection: Selection;
  laneColorOverrides: LaneColorOverrides;
  dark: boolean;
  onSelectLane: (laneId: string) => void;
  onSelectRecord: (sel: Selection) => void;
}) {
  const [query, setQuery] = useState("");
  const [showClosed, setShowClosed] = useState(false);
  const [showUndescribed, setShowUndescribed] = useState(false);

  const overviews = useMemo(() => laneOverviews(doc), [doc]);
  const hits = useMemo(() => searchLanes(doc, query), [doc, query]);
  const open = overviews.filter((lane) => lane.status === "open");
  const closed = overviews.filter((lane) => lane.status === "closed");
  const searching = query.trim().length > 0;

  const laneVars = (laneId: string): CSSProperties => {
    const colors = laneColors(doc, laneId, laneColorOverrides, dark);
    return { "--lane-color": colors.laneColor, "--lane-bg": colors.laneBg } as CSSProperties;
  };

  const selectedLaneId = selection?.kind === "lane" ? selection.id : null;
  // Lanes with a written summary or purpose read at a glance; the rest are
  // structural noise in a large run, so they fold behind a count the same way
  // closed lanes do. The current/selected lane always stays visible.
  const described = open.filter(
    (lane) =>
      lane.summary_text ||
      lane.purpose ||
      lane.lane_id === activeLaneId ||
      lane.lane_id === selectedLaneId,
  );
  const undescribed = open.filter((lane) => !described.includes(lane));

  return (
    <aside className="lane-sidebar">
      <div className="lane-sidebar-title">
        <strong>Explorer</strong>
        <span>Search every lane and record</span>
      </div>
      <div className="lane-sidebar-search">
        <input
          type="search"
          aria-label="search lanes and records"
          placeholder="search this run…"
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
        />
        <div className="lane-search-shortcuts" aria-label="Suggested searches">
          {["blocker", "question", "failed"].map((term) => (
            <button type="button" key={term} onClick={() => setQuery(term)}>
              {term}
            </button>
          ))}
        </div>
      </div>

      {searching ? (
        <div className="lane-sidebar-body">
          <h3 className="lane-sidebar-heading">
            {hits.length} {hits.length === 1 ? "lane" : "lanes"} match
          </h3>
          {hits.length === 0 && <p className="muted lane-sidebar-empty">no matches</p>}
          {hits.map((hit) => {
            const targets = hitTargets(doc, hit);
            return (
              <article key={hit.lane_id} className="lane-hit" style={laneVars(hit.lane_id)}>
                <button
                  type="button"
                  className="lane-hit-head"
                  onClick={() => onSelectLane(hit.lane_id)}
                >
                  <span className="lane-color-dot" style={{ backgroundColor: "var(--lane-color)" }} />
                  <span className="lane-name">{hit.label}</span>
                  <span className={`lane-status-badge ${hit.status}`}>{hit.status}</span>
                </button>
                <p className="lane-hit-snippet">{hit.snippet}</p>
                {targets.length > 0 && (
                  <div className="lane-hit-targets">
                    {targets.slice(0, 6).map((target) => (
                      <button
                        key={`${target.kind}:${target.id}`}
                        type="button"
                        className="record-id-chip lane-hit-target"
                        title={`jump to ${target.kind} ${target.id}`}
                        onClick={() => onSelectRecord(target)}
                      >
                        {target.kind === "node" ? "n" : "t"}:{target.id.slice(2, 10)}
                      </button>
                    ))}
                    {targets.length > 6 && (
                      <span className="muted">+{targets.length - 6} more</span>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="lane-sidebar-body">
          <h3 className="lane-sidebar-heading">lanes ({overviews.length})</h3>
          {overviews.length === 0 && <p className="muted lane-sidebar-empty">no lanes yet</p>}
          {described.map((lane) => (
            <button
              key={lane.lane_id}
              type="button"
              className={`lane-row${lane.lane_id === selectedLaneId ? " selected" : ""}${
                lane.lane_id === activeLaneId ? " current" : ""
              }`}
              style={laneVars(lane.lane_id)}
              onClick={() => onSelectLane(lane.lane_id)}
            >
              <span className="lane-row-head">
                <span className="lane-color-dot" style={{ backgroundColor: "var(--lane-color)" }} />
                <span className="lane-name">{lane.label}</span>
                {lane.lane_id === activeLaneId && <span className="active-badge">current</span>}
              </span>
              <span className="lane-row-summary">
                {collapseSummary(lane.summary_text) || lane.purpose || "(no summary yet)"}
              </span>
            </button>
          ))}

          {undescribed.length > 0 && (
            <>
              <button
                type="button"
                className="lane-closed-toggle"
                onClick={() => setShowUndescribed(!showUndescribed)}
              >
                {showUndescribed ? "▾" : "▸"} {undescribed.length}{" "}
                {undescribed.length === 1 ? "lane" : "lanes"} without a summary
              </button>
              {showUndescribed &&
                undescribed.map((lane) => (
                  <button
                    key={lane.lane_id}
                    type="button"
                    className={`lane-row${lane.lane_id === selectedLaneId ? " selected" : ""}`}
                    style={laneVars(lane.lane_id)}
                    onClick={() => onSelectLane(lane.lane_id)}
                  >
                    <span className="lane-row-head">
                      <span
                        className="lane-color-dot"
                        style={{ backgroundColor: "var(--lane-color)" }}
                      />
                      <span className="lane-name">{lane.label}</span>
                    </span>
                    <span className="lane-row-summary">(no summary yet)</span>
                  </button>
                ))}
            </>
          )}

          {closed.length > 0 && (
            <>
              <button
                type="button"
                className="lane-closed-toggle"
                onClick={() => setShowClosed(!showClosed)}
              >
                {showClosed ? "▾" : "▸"} {closed.length} closed{" "}
                {closed.length === 1 ? "lane" : "lanes"}
              </button>
              {showClosed &&
                closed.map((lane) => (
                  <button
                    key={lane.lane_id}
                    type="button"
                    className={`lane-row lane-row-closed${
                      lane.lane_id === selectedLaneId ? " selected" : ""
                    }`}
                    style={laneVars(lane.lane_id)}
                    onClick={() => onSelectLane(lane.lane_id)}
                  >
                    <span className="lane-row-head">
                      <span
                        className="lane-color-dot"
                        style={{ backgroundColor: "var(--lane-color)" }}
                      />
                      <span className="lane-name">{lane.label}</span>
                      <span className="lane-status-badge closed">closed</span>
                    </span>
                    <span className="lane-row-summary">
                      {collapseSummary(lane.summary_text) || lane.purpose || "(no summary)"}
                    </span>
                  </button>
                ))}
            </>
          )}
        </div>
      )}
    </aside>
  );
}
