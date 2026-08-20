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
import type { RunDocument, RunPayload } from "./types";

export const TAG_TYPE = "tag";
export const SUMMARY_TYPE = "topic_summary";

export interface TopicRecord {
  recordId: string;
  kind: "node" | "step";
  active: boolean;
  note: string | null;
}

export interface TopicSummary {
  payloadId: string;
  targetId: string;
  text: string;
  sources: string[];
}

export interface TopicView {
  name: string;
  summary: TopicSummary | null;
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
    records.push({
      recordId,
      kind: node ? "node" : "step",
      active: node ? !node.inactive : !step!.inactive,
      note: typeof note === "string" ? note : null,
    });
  }
  return records;
}

function currentSummary(doc: RunDocument, name: string): TopicSummary | null {
  const rank = recordEventRank(doc);
  let best: { rank: number; payload: RunPayload } | null = null;
  for (const payload of doc.payloads) {
    if (payload.type !== SUMMARY_TYPE || payloadTopic(payload) !== name) continue;
    const payloadRank = rank.get(payload.payload_id) ?? -1;
    // >= so equal ranks fall back to append order (payloads written without
    // a lane/user carry no work event and all rank -1).
    if (best === null || payloadRank >= best.rank) best = { rank: payloadRank, payload };
  }
  if (!best) return null;
  const content = best.payload.content ?? {};
  const sources = Array.isArray(content.sources) ? content.sources.map(String) : [];
  return {
    payloadId: best.payload.payload_id,
    targetId: best.payload.target_id,
    text: String(content.text ?? ""),
    sources,
  };
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
  const islands = [...groups.values()];
  islands.sort((a, b) => activeIds.indexOf(a[0]) - activeIds.indexOf(b[0]));
  return { islands, inactive };
}

export function topicView(doc: RunDocument, name: string): TopicView {
  const records = tagRecords(doc, name);
  const { islands, inactive } = topicIslands(doc, records);
  return { name, summary: currentSummary(doc, name), islands, inactive, records };
}

export function listTopics(doc: RunDocument): TopicView[] {
  return topicNames(doc).map((name) => topicView(doc, name));
}
