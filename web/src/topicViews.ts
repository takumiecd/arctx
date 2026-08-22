// Derived topics — the TypeScript mirror of arctx/core/topics.py. Keep the
// two in sync (same contract rule as types.ts and trialTables.ts).
//
// A topic is a flat name carried by plain generic payloads: type="tag" marks
// membership of a node/step, type="topic_summary" is the subject's current
// statement (latest by work-event rank wins, append order breaks ties).
// Islands group the tagged records by lineage: two records share an island
// when one derives from the other over the active graph, transitively through
// tagged records. Sibling branches are separate islands — the join-candidate
// signal — because everything in a run hangs off the root, so mere
// connectivity would collapse every topic into one island.

import { recordEventRank } from "./lanes";
import { laneIdForRecord, laneLabel, provenanceFor, recordLabel } from "./model";
import type { RunDocument, RunPayload } from "./types";

export const TAG_TYPE = "tag";
export const SUMMARY_TYPE = "topic_summary";

export interface TopicRecord {
  recordId: string;
  kind: "node" | "step";
  active: boolean;
  note: string | null;
  // Derived for display: a record reads as the work it stands for, not as an
  // opaque id. Same derivation the graph view uses for its node labels.
  label: string;
  laneName: string | null;
  createdAt: string | null;
}

export interface TopicSummary {
  payloadId: string;
  targetId: string;
  text: string;
  sources: string[];
  createdAt: string | null;
  userId: string | null;
}

export interface TopicView {
  name: string;
  summary: TopicSummary | null;
  history: TopicSummary[]; // oldest first; last entry is the current belief
  islands: string[][];
  inactive: string[];
  records: TopicRecord[];
}

function payloadTopic(payload: RunPayload): string | null {
  if (payload.type !== TAG_TYPE && payload.type !== SUMMARY_TYPE) return null;
  const topic = payload.content?.topic;
  return typeof topic === "string" && topic.trim() ? topic : null;
}

export function topicNames(doc: RunDocument): string[] {
  const seen: string[] = [];
  for (const payload of doc.payloads) {
    const topic = payloadTopic(payload);
    if (topic !== null && !seen.includes(topic)) seen.push(topic);
  }
  return seen;
}

function tagRecords(doc: RunDocument, name: string): TopicRecord[] {
  const nodes = new Map(doc.nodes.map((node) => [node.node_id, node]));
  const steps = new Map(doc.steps.map((step) => [step.step_id, step]));
  const records: TopicRecord[] = [];
  const seen = new Set<string>();
  for (const payload of doc.payloads) {
    if (payload.type !== TAG_TYPE || payloadTopic(payload) !== name) continue;
    const recordId = payload.target_id;
    if (seen.has(recordId)) continue;
    seen.add(recordId);
    const node = nodes.get(recordId);
    const step = steps.get(recordId);
    if (!node && !step) continue;
    const note = payload.content?.note;
    const laneId = laneIdForRecord(doc, recordId);
    records.push({
      recordId,
      kind: node ? "node" : "step",
      active: node ? !node.inactive : !step!.inactive,
      note: typeof note === "string" ? note : null,
      label: recordLabel(doc, recordId),
      laneName: laneId ? laneLabel(doc, laneId) : null,
      createdAt: provenanceFor(doc, recordId)?.created_at ?? null,
    });
  }
  return records;
}

// Every statement ever written about the topic, oldest first — the current
// belief is the last entry, the rest is how the belief evolved (supersession
// never deletes). Rank order with append order as the tie-break.
function summaryHistory(doc: RunDocument, name: string): TopicSummary[] {
  const rank = recordEventRank(doc);
  const eventByRecord = new Map<string, { createdAt: string | null; userId: string | null }>();
  for (const event of doc.work_events ?? []) {
    for (const recordId of event.created_records ?? []) {
      if (!eventByRecord.has(recordId)) {
        eventByRecord.set(recordId, {
          createdAt: event.created_at ?? null,
          userId: event.user_id ?? null,
        });
      }
    }
  }
  const entries: { rank: number; order: number; summary: TopicSummary }[] = [];
  doc.payloads.forEach((payload, order) => {
    if (payload.type !== SUMMARY_TYPE || payloadTopic(payload) !== name) return;
    const content = payload.content ?? {};
    const sources = Array.isArray(content.sources) ? content.sources.map(String) : [];
    const provenance = eventByRecord.get(payload.payload_id);
    entries.push({
      rank: rank.get(payload.payload_id) ?? -1,
      order,
      summary: {
        payloadId: payload.payload_id,
        targetId: payload.target_id,
        text: String(content.text ?? ""),
        sources,
        createdAt: provenance?.createdAt ?? null,
        userId: provenance?.userId ?? null,
      },
    });
  });
  entries.sort((a, b) => a.rank - b.rank || a.order - b.order);
  return entries.map((entry) => entry.summary);
}

function forwardAdjacency(doc: RunDocument): Map<string, string[]> {
  const inactiveNodes = new Set(doc.nodes.filter((n) => n.inactive).map((n) => n.node_id));
  const adjacency = new Map<string, string[]>();
  const push = (from: string, to: string) => {
    const list = adjacency.get(from);
    if (list) list.push(to);
    else adjacency.set(from, [to]);
  };
  for (const step of doc.steps) {
    if (step.inactive) continue;
    for (const nodeId of step.input_node_ids) {
      if (!inactiveNodes.has(nodeId)) push(nodeId, step.step_id);
    }
    if (!inactiveNodes.has(step.output_node_id)) push(step.step_id, step.output_node_id);
  }
  return adjacency;
}

function descendants(adjacency: Map<string, string[]>, start: string): Set<string> {
  const seen = new Set<string>();
  const queue = [start];
  while (queue.length) {
    for (const child of adjacency.get(queue.pop()!) ?? []) {
      if (!seen.has(child)) {
        seen.add(child);
        queue.push(child);
      }
    }
  }
  return seen;
}

export function topicIslands(
  doc: RunDocument,
  records: TopicRecord[],
): { islands: string[][]; inactive: string[] } {
  const adjacency = forwardAdjacency(doc);
  const activeIds = records.filter((r) => r.active).map((r) => r.recordId);
  const inactive = records.filter((r) => !r.active).map((r) => r.recordId);
  const reach = new Map(activeIds.map((id) => [id, descendants(adjacency, id)]));

  const parent = new Map(activeIds.map((id) => [id, id]));
  const find = (x: string): string => {
    let root = x;
    while (parent.get(root) !== root) root = parent.get(root)!;
    return root;
  };
  for (let i = 0; i < activeIds.length; i++) {
    for (let j = i + 1; j < activeIds.length; j++) {
      const a = activeIds[i];
      const b = activeIds[j];
      if (reach.get(a)!.has(b) || reach.get(b)!.has(a)) parent.set(find(a), find(b));
    }
  }
  const groups = new Map<string, string[]>();
  for (const id of activeIds) {
    const root = find(id);
    const group = groups.get(root);
    if (group) group.push(id);
    else groups.set(root, [id]);
  }
  // Oldest first inside an island: a record that reaches more members comes
  // earlier (a linear extension of the reachability order), with tag order
  // breaking ties between unrelated siblings. Islands themselves keep
  // first-appearance order so island numbers stay stable.
  const islands = [...groups.values()].map((members) =>
    [...members].sort(
      (a, b) =>
        members.filter((other) => reach.get(b)!.has(other)).length -
          members.filter((other) => reach.get(a)!.has(other)).length ||
        activeIds.indexOf(a) - activeIds.indexOf(b),
    ),
  );
  islands.sort(
    (a, b) =>
      Math.min(...a.map((id) => activeIds.indexOf(id))) -
      Math.min(...b.map((id) => activeIds.indexOf(id))),
  );
  return { islands, inactive };
}

// An island's frontier: the members no other member derives from. These are
// the records a join takes as inputs — joining anything upstream of them
// would fork the lineage instead of continuing it. Mirrors
// arctx.core.topics.island_tips.
export function islandTips(doc: RunDocument, island: string[]): string[] {
  const adjacency = forwardAdjacency(doc);
  const reach = new Map(island.map((id) => [id, descendants(adjacency, id)]));
  return island.filter(
    (id) => !island.some((other) => other !== id && reach.get(id)!.has(other)),
  );
}

// Which islands a statement speaks for. A statement is anchored by what it
// cites (sources) and by the node it was written on; an island counts as
// covered when one of those anchors is a member or descends from one. One
// island means it speaks for that lineage alone (so another island's
// statement would silently supersede it); two or more means the author
// already reconciled them in prose. Mirrors
// arctx.core.topics.statement_islands.
export function statementIslands(
  doc: RunDocument,
  islands: string[][],
  summary: TopicSummary,
): Set<number> {
  const adjacency = forwardAdjacency(doc);
  const anchors = new Set<string>(summary.sources);
  if (summary.targetId) anchors.add(summary.targetId);
  const covered = new Set<number>();
  if (!anchors.size) return covered;
  islands.forEach((island, index) => {
    for (const member of island) {
      if (anchors.has(member)) {
        covered.add(index);
        return;
      }
      const reach = descendants(adjacency, member);
      for (const anchor of anchors) {
        if (reach.has(anchor)) {
          covered.add(index);
          return;
        }
      }
    }
  });
  return covered;
}

// Per-island latest statement, plus the newest one that covers two or more
// islands — the prose in which the subject was already settled.
export function islandStatements(
  doc: RunDocument,
  view: TopicView,
): { perIsland: (TopicSummary | null)[]; reconciling: TopicSummary | null } {
  const perIsland: (TopicSummary | null)[] = view.islands.map(() => null);
  let reconciling: TopicSummary | null = null;
  for (const summary of view.history) {
    const covered = statementIslands(doc, view.islands, summary);
    if (covered.size === 1) perIsland[[...covered][0]] = summary;
    else if (covered.size > 1) reconciling = summary;
  }
  return { perIsland, reconciling };
}

export function topicView(doc: RunDocument, name: string): TopicView {
  const records = tagRecords(doc, name);
  const { islands, inactive } = topicIslands(doc, records);
  const history = summaryHistory(doc, name);
  return {
    name,
    summary: history.length ? history[history.length - 1] : null,
    history,
    islands,
    inactive,
    records,
  };
}

export function listTopics(doc: RunDocument): TopicView[] {
  return topicNames(doc).map((name) => topicView(doc, name));
}
