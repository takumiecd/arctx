// "Flow" tab card showing who/what lane created the selected record.

import type { CSSProperties } from "react";

import type { RunDocument } from "../types";
import { laneColors, laneLabel, provenanceFor, type LaneColorOverrides } from "../model";
import type { DetailUnit } from "./types";

export function ProvenanceCard({
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
          attribution was recorded, or without a lane.
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

export function laneVars(
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
