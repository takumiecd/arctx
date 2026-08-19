// Flat lane retrieval, client-side. This is the TS mirror of `arctx.core.lanes`
// (the module behind `arctx explore`): lanes are flat git-branch-like work
// units — no parents, no children, no breadcrumbs — and retrieval is
// summary-first plus search.
//
// Everything here is derived from the already-loaded run document, so the lane
// list and the search box never need a server round-trip.

import type { RunDocument, RunLane, RunPayload } from "./types";

export interface LaneOverview {
  lane_id: string;
  label: string;
  name: string | null;
  status: "open" | "closed";
  purpose: string | null;
  started_at: string | null;
  closed_at: string | null;
  summary_text: string | null;
  summary_payload_id: string | null;
  summary_node_id: string | null;
  node_count: number;
  step_count: number;
  payload_count: number;
  active_frontier_node_ids: string[];
}

export interface LaneSearchHit {
  lane_id: string;
  label: string;
  status: "open" | "closed";
  snippet: string;
  name_match: boolean;
  matched_record_ids: string[];
  matched_payload_ids: string[];
}

// record_id -> position in the append-only work-event ledger. jsonl line order
// is meaningless after a union merge, so `WorkEvent.created_records` is the
// durable ordering signal (mirrors `arctx.core.lanes.record_event_rank`).
export function recordEventRank(doc: RunDocument): Map<string, number> {
  const rank = new Map<string, number>();
  (doc.work_events ?? []).forEach((event, index) => {
    for (const recordId of event.created_records ?? []) {
      if (!rank.has(recordId)) rank.set(recordId, index);
    }
  });
  return rank;
}

export function lanePurpose(lane: RunLane | null | undefined): string | null {
  const purpose = lane?.metadata?.purpose;
  const text = typeof purpose === "string" ? purpose.trim() : "";
  return text || null;
}

export function collapseSummary(text: string | null | undefined, limit = 160): string {
  if (!text) return "";
  const first = text.split("\n").map((line) => line.trim()).find((line) => line) ?? "";
  if (first.length <= limit) return first;
  return `${first.slice(0, Math.max(0, limit - 3)).trimEnd()}...`;
}

function laneOfRecord(doc: RunDocument, recordId: string): string | null {
  return doc.record_provenance?.[recordId]?.lane_id ?? null;
}

// A lane's summary payloads, oldest first in work-event order. Both
// `lane close` and `lane summarize` attach one; the last one wins.
export function laneSummaryPayloads(doc: RunDocument, laneId: string): RunPayload[] {
  const rank = recordEventRank(doc);
  return doc.payloads
    .filter(
      (payload) =>
        payload.payload_type === "summary" &&
        laneOfRecord(doc, payload.payload_id) === laneId,
    )
    .sort((a, b) => {
      const ra = rank.get(a.payload_id) ?? -1;
      const rb = rank.get(b.payload_id) ?? -1;
      if (ra !== rb) return ra - rb;
      return a.payload_id.localeCompare(b.payload_id);
    });
}

export function laneCurrentSummary(doc: RunDocument, laneId: string): RunPayload | null {
  const payloads = laneSummaryPayloads(doc, laneId);
  return payloads.length ? payloads[payloads.length - 1] : null;
}

export function laneOverview(doc: RunDocument, lane: RunLane): LaneOverview {
  const summary = laneCurrentSummary(doc, lane.lane_id);
  const group = (doc.groups ?? []).find(
    (candidate) => candidate.kind === "lane" && candidate.lane_id === lane.lane_id,
  );
  const payloadCount = doc.payloads.filter(
    (payload) => laneOfRecord(doc, payload.payload_id) === lane.lane_id,
  ).length;
  const inactiveSteps = new Set(
    doc.steps.filter((step) => step.inactive).map((step) => step.step_id),
  );
  const inactiveNodes = new Set(
    doc.nodes.filter((node) => node.inactive).map((node) => node.node_id),
  );
  const laneNodeIds = new Set(group?.node_ids ?? []);
  const activeFrontiers = [...laneNodeIds]
    .filter(
      (nodeId) =>
        !inactiveNodes.has(nodeId) &&
        doc.steps.every(
          (step) => !step.input_node_ids.includes(nodeId) || inactiveSteps.has(step.step_id),
        ),
    )
    .sort();
  return {
    lane_id: lane.lane_id,
    label: lane.name || lane.lane_id,
    name: lane.name ?? null,
    status: lane.status === "closed" ? "closed" : "open",
    purpose: lanePurpose(lane),
    started_at: lane.started_at ?? null,
    closed_at: lane.closed_at ?? null,
    summary_text: typeof summary?.text === "string" ? summary.text : null,
    summary_payload_id: summary?.payload_id ?? null,
    summary_node_id: summary?.target_id ?? null,
    node_count: group?.node_ids.length ?? 0,
    step_count: group?.step_ids.length ?? 0,
    payload_count: payloadCount,
    active_frontier_node_ids: activeFrontiers,
  };
}

// Open lanes first (oldest first), then closed ones — the order `arctx explore`
// prints, so both surfaces read the same way.
export function laneOverviews(doc: RunDocument): LaneOverview[] {
  return (doc.lanes ?? [])
    .map((lane) => laneOverview(doc, lane))
    .sort((a, b) => {
      if ((a.status === "open") !== (b.status === "open")) return a.status === "open" ? -1 : 1;
      const sa = a.started_at ?? "";
      const sb = b.started_at ?? "";
      if (sa !== sb) return sa < sb ? -1 : 1;
      return a.lane_id.localeCompare(b.lane_id);
    });
}

// Opaque ids are never what a human searches for, and leaking them into the
// haystack fills snippets with UUID noise (mirrors `_NON_SEARCHABLE_KEYS`).
const NON_SEARCHABLE_KEYS = new Set([
  "payload_id",
  "target_id",
  "target_kind",
  "payload_type",
  "step_id",
  "node_id",
  "input_node_ids",
  "output_node_id",
  "lane_id",
]);

function searchableText(value: unknown): string[] {
  if (value === null || value === undefined) return [];
  if (Array.isArray(value)) return value.flatMap(searchableText);
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !NON_SEARCHABLE_KEYS.has(key))
      .flatMap(([, item]) => searchableText(item));
  }
  return [String(value)];
}

// Whitespace-separated terms, case-insensitive AND. The haystack for a lane is
// its name + purpose + every payload it owns (created by it, or attached to a
// record it owns). Position-independent: no current lane, no descent.
export function searchLanes(
  doc: RunDocument,
  query: string,
  snippetChars = 180,
): LaneSearchHit[] {
  const terms = query.split(/\s+/).filter(Boolean).map((term) => term.toLowerCase());
  if (terms.length === 0) return [];

  const byLane = new Map<string, RunPayload[]>();
  for (const payload of doc.payloads) {
    const owner = laneOfRecord(doc, payload.payload_id) ?? laneOfRecord(doc, payload.target_id);
    if (!owner) continue;
    const bucket = byLane.get(owner);
    if (bucket) bucket.push(payload);
    else byLane.set(owner, [payload]);
  }

  const hits: LaneSearchHit[] = [];
  for (const lane of doc.lanes ?? []) {
    const label = lane.name || lane.lane_id;
    const parts: string[] = [label];
    const purpose = lanePurpose(lane);
    if (purpose) parts.push(purpose);

    const matchedPayloadIds: string[] = [];
    const matchedRecordIds: string[] = [];
    for (const payload of byLane.get(lane.lane_id) ?? []) {
      const texts = searchableText(payload);
      parts.push(...texts);
      const folded = texts.join("\n").toLowerCase();
      if (terms.some((term) => folded.includes(term))) {
        matchedPayloadIds.push(payload.payload_id);
        matchedRecordIds.push(payload.target_id);
      }
    }

    const haystack = parts.join("\n");
    const folded = haystack.toLowerCase();
    if (!terms.every((term) => folded.includes(term))) continue;

    const index = folded.indexOf(terms[0]);
    const start = Math.max(0, index - 45);
    hits.push({
      lane_id: lane.lane_id,
      label,
      status: lane.status === "closed" ? "closed" : "open",
      snippet: haystack.slice(start, start + snippetChars).split(/\s+/).join(" ").trim(),
      name_match: terms.some((term) => label.toLowerCase().includes(term)),
      matched_record_ids: [...new Set(matchedRecordIds)],
      matched_payload_ids: [...new Set(matchedPayloadIds)],
    });
  }

  hits.sort((a, b) => {
    if (a.name_match !== b.name_match) return a.name_match ? -1 : 1;
    return a.label.toLowerCase().localeCompare(b.label.toLowerCase());
  });
  return hits;
}

// Where a search hit should jump to: the record the matched payload is attached
// to, so clicking a result lands on the node/step in the graph.
export function hitTargets(
  doc: RunDocument,
  hit: LaneSearchHit,
): { kind: "node" | "step"; id: string }[] {
  const nodeIds = new Set(doc.nodes.map((node) => node.node_id));
  const stepIds = new Set(doc.steps.map((step) => step.step_id));
  const out: { kind: "node" | "step"; id: string }[] = [];
  for (const id of hit.matched_record_ids) {
    if (nodeIds.has(id)) out.push({ kind: "node", id });
    else if (stepIds.has(id)) out.push({ kind: "step", id });
  }
  return out;
}
