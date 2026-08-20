import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";

import { collapseSummary, laneOverviews, recordEventRank, type LaneOverview } from "./lanes";
import {
  laneColors,
  laneIdForRecord,
  laneLabel,
  nodeLabel,
  nodeSummaryText,
  stepType,
  type LaneColorOverrides,
} from "./model";
import { payloadDisplayFor } from "./payloadExtensions";
import { listTopics } from "./topicViews";
import type { RunDocument, RunPayload, RunStep, RunWorkEvent } from "./types";

type RecordSelection = { kind: "node" | "step"; id: string };

interface PathPoint {
  nodeId: string;
  viaStep: RunStep | null;
}

interface NearbyNode {
  nodeId: string;
  viaStep: RunStep | null;
}

const ATTENTION_TYPES = new Set([
  "request",
  "question",
  "blocker",
  "approval",
  "issue",
  "risk",
  "failure",
  "failed",
  "error",
]);
const RESOLVED_STATES = new Set(["answered", "closed", "done", "resolved"]);

export function Overview({
  doc,
  currentLaneId,
  laneColorOverrides,
  dark,
  onSelectRecord,
  onOpenGraph,
  onOpenTopics,
}: {
  doc: RunDocument;
  currentLaneId: string | null;
  laneColorOverrides: LaneColorOverrides;
  dark: boolean;
  onSelectRecord: (selection: RecordSelection) => void;
  onOpenGraph: () => void;
  onOpenTopics: () => void;
}) {
  const lanes = useMemo(() => laneOverviews(doc), [doc]);
  const currentLane = lanes.find((lane) => lane.lane_id === currentLaneId) ?? null;
  const initialNodeId = useMemo(
    () => preferredFocusNode(doc, currentLane, lanes),
    [doc, currentLaneId],
  );
  const [focusNodeId, setFocusNodeId] = useState(initialNodeId);

  useEffect(() => setFocusNodeId(initialNodeId), [doc.run_id, currentLaneId, initialNodeId]);

  const focusNode = doc.nodes.find((node) => node.node_id === focusNodeId) ?? null;
  const focusLaneId = focusNodeId ? laneIdForRecord(doc, focusNodeId) : null;
  const focusLane = lanes.find((lane) => lane.lane_id === focusLaneId) ?? currentLane;
  const path = focusNodeId ? primaryPath(doc, focusNodeId) : [];
  const neighborhood = focusNodeId ? nearbyNodes(doc, focusNodeId) : emptyNeighborhood();
  const currentFrontiers = currentLane?.active_frontier_node_ids ?? [];
  const isCurrentFrontier = Boolean(
    focusNodeId && focusLaneId === currentLaneId && currentFrontiers.includes(focusNodeId),
  );
  const depth = Math.max(0, path.length - 1);
  const sinceSummary = stepsSinceSummary(doc, path);
  const attention = useMemo(() => attentionPayloads(doc), [doc]);
  const recent = useMemo(() => recentEvents(doc), [doc]);

  const laneVars = (laneId: string): CSSProperties => {
    const colors = laneColors(doc, laneId, laneColorOverrides, dark);
    return { "--lane-color": colors.laneColor, "--lane-bg": colors.laneBg } as CSSProperties;
  };

  const inspectFocus = () => {
    if (focusNodeId) onSelectRecord({ kind: "node", id: focusNodeId });
    else onOpenGraph();
  };

  const returnToCurrent = () => {
    const nodeId = preferredFocusNode(doc, currentLane, lanes);
    if (nodeId) setFocusNodeId(nodeId);
  };

  return (
    <section className="overview context-overview" aria-label="Run context overview">
      <div className="overview-inner context-overview-inner">
        <section className="context-hero" style={focusLaneId ? laneVars(focusLaneId) : undefined}>
          <div className="context-hero-main">
            <p className="overview-eyebrow">
              {isCurrentFrontier ? "CURRENT STATE" : "CONTEXT VIEW"}
            </p>
            <div className="context-title-row">
              <h1>{focusLane?.label ?? doc.run_id}</h1>
              {focusLaneId === currentLaneId && <span className="context-current-badge">current lane</span>}
            </div>
            <p className="context-summary">
              {collapseSummary(focusLane?.summary_text, 260) ||
                focusLane?.purpose ||
                "No lane summary yet. The graph position below is derived from recorded steps."}
            </p>
            <div className="context-position-facts" aria-label="Structural position">
              <PositionFact label="position" value={positionLabel(focusNode?.inactive ?? false, neighborhood.ahead.length)} />
              <PositionFact label="from root" value={`${depth} steps`} />
              <PositionFact label="since summary" value={`${sinceSummary} steps`} />
              <PositionFact
                label="lane frontiers"
                value={String(focusLane?.active_frontier_node_ids.length ?? 0)}
              />
            </div>
          </div>
          <div className="context-hero-actions">
            {!isCurrentFrontier && currentLane && (
              <button type="button" className="context-secondary-action" onClick={returnToCurrent}>
                Return to current
              </button>
            )}
            <button type="button" className="overview-primary-action" onClick={inspectFocus}>
              Inspect in graph <span aria-hidden="true">→</span>
            </button>
          </div>
        </section>

        {currentFrontiers.length > 1 && focusLaneId === currentLaneId && (
          <section className="frontier-switcher" aria-label="Current lane frontiers">
            <span>{currentFrontiers.length} current frontiers</span>
            <div>
              {sortNodesByRecency(doc, currentFrontiers).map((nodeId, index) => (
                <button
                  type="button"
                  className={focusNodeId === nodeId ? "active" : ""}
                  key={nodeId}
                  onClick={() => setFocusNodeId(nodeId)}
                >
                  {index + 1}. {nodeLabel(doc, nodeId)}
                </button>
              ))}
            </div>
          </section>
        )}

        <TopicsStrip doc={doc} onOpenTopics={onOpenTopics} />

        <div className="state-grid">
          <StateColumn title="Current endpoints" subtitle="where work can continue">
            {(focusLane?.active_frontier_node_ids ?? []).length === 0 ? (
              <div className="state-empty">This lane has no active frontier.</div>
            ) : (
              sortNodesByRecency(doc, focusLane?.active_frontier_node_ids ?? []).slice(0, 6).map((nodeId) => (
                <button
                  type="button"
                  className={`state-row${nodeId === focusNodeId ? " active" : ""}`}
                  key={nodeId}
                  onClick={() => setFocusNodeId(nodeId)}
                >
                  <span className="state-row-kind">frontier</span>
                  <span>
                    <strong>{nodeLabel(doc, nodeId)}</strong>
                    <small>{frontierSummary(doc, nodeId)}</small>
                  </span>
                </button>
              ))
            )}
          </StateColumn>

          <StateColumn title="Known issues & questions" subtitle="what may need attention">
            {attention.length === 0 ? (
              <div className="state-empty">No open blocker, question, or approval was found.</div>
            ) : (
              attention.slice(0, 6).map((payload) => {
                const display = payloadDisplayFor(payload, doc);
                return (
                  <button
                    type="button"
                    className="state-row"
                    key={payload.payload_id}
                    onClick={() => onSelectRecord({ kind: payload.target_kind, id: payload.target_id })}
                  >
                    <span className={`attention-kind ${attentionType(payload)}`}>{attentionType(payload)}</span>
                    <span>
                      <strong>{display.summary || display.title}</strong>
                      <small>{laneNameForPayload(doc, payload)}</small>
                    </span>
                  </button>
                );
              })
            )}
          </StateColumn>

          <StateColumn title="What just happened" subtitle="latest recorded work">
            {recent.length === 0 ? (
              <div className="state-empty">No work events have been recorded.</div>
            ) : (
              recent.slice(0, 7).map((event) => {
                const target = eventTarget(doc, event);
                const content = (
                  <>
                    <span className="state-row-kind">{humanize(event.event_type)}</span>
                    <span>
                      <strong>{event.summary || humanize(event.event_type)}</strong>
                      <small>{laneLabel(doc, event.lane_id)}{event.created_at ? ` · ${formatTime(event.created_at)}` : ""}</small>
                    </span>
                  </>
                );
                return target ? (
                  <button type="button" className="state-row" key={event.event_id} onClick={() => onSelectRecord(target)}>
                    {content}
                  </button>
                ) : (
                  <div className="state-row static" key={event.event_id}>{content}</div>
                );
              })
            )}
          </StateColumn>
        </div>

        <details className="context-trace-details">
          <summary>
            <span>
              <strong>Explore this position</strong>
              <small>Path from root and one-hop inputs, alternatives, and children</small>
            </span>
            <span aria-hidden="true">⌄</span>
          </summary>
          <section className="context-section path-section">
            <ContextHeading
              kicker="FLOW"
              title="Path to here"
              description="The primary recorded route into the focused node."
            />
            <PathRail doc={doc} path={path} focusNodeId={focusNodeId} onFocus={setFocusNodeId} />
          </section>
          <section className="context-section">
            <ContextHeading
              kicker="LOCAL CONTEXT"
              title="Nearby routes"
              description="Move one hop backward, sideways, or forward."
            />
            <div className="nearby-grid">
              <NearbyColumn title="Inputs" hint="what led here" items={neighborhood.inputs} empty="This is the run root." doc={doc} onFocus={setFocusNodeId} />
              <NearbyColumn title="Alternatives" hint="sibling routes" items={neighborhood.alternatives} empty="No sibling branch from the preceding state." doc={doc} onFocus={setFocusNodeId} />
              <NearbyColumn title="Ahead" hint="what follows" items={neighborhood.ahead} empty={focusNode?.inactive ? "This route is inactive." : "No active child — this node is a frontier."} doc={doc} onFocus={setFocusNodeId} />
            </div>
          </section>
        </details>
      </div>
    </section>
  );
}

function PositionFact({ label, value }: { label: string; value: string }) {
  return (
    <span className="position-fact">
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  );
}

function StateColumn({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <section className="state-column">
      <header>
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </header>
      <div className="state-column-body">{children}</div>
    </section>
  );
}

function ContextHeading({
  kicker,
  title,
  description,
}: {
  kicker: string;
  title: string;
  description: string;
}) {
  return (
    <div className="context-section-heading">
      <p>{kicker}</p>
      <div>
        <h2>{title}</h2>
        <span>{description}</span>
      </div>
    </div>
  );
}

function PathRail({
  doc,
  path,
  focusNodeId,
  onFocus,
}: {
  doc: RunDocument;
  path: PathPoint[];
  focusNodeId: string | null;
  onFocus: (nodeId: string) => void;
}) {
  if (!path.length) return <div className="context-empty">No graph position is available yet.</div>;
  const visible = path.slice(-6);
  const hidden = path.length - visible.length;
  return (
    <div className="path-rail-wrap">
      <div className="path-rail">
        {hidden > 0 && <span className="path-omitted">+{hidden} earlier</span>}
        {visible.map((point, index) => (
          <div className="path-segment" key={point.nodeId}>
            {(index > 0 || hidden > 0) && (
              <span className="path-step-label">
                {point.viaStep ? stepType(doc, point.viaStep.step_id) : "step"}
                <span aria-hidden="true">→</span>
              </span>
            )}
            <button
              type="button"
              className={`path-node${point.nodeId === focusNodeId ? " focused" : ""}`}
              onClick={() => onFocus(point.nodeId)}
            >
              <span>{point.nodeId === doc.root_node_id ? "start" : "node"}</span>
              <strong>{nodeLabel(doc, point.nodeId)}</strong>
              {nodeSummaryText(doc, point.nodeId) && <small>summary</small>}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function NearbyColumn({
  title,
  hint,
  items,
  empty,
  doc,
  onFocus,
}: {
  title: string;
  hint: string;
  items: NearbyNode[];
  empty: string;
  doc: RunDocument;
  onFocus: (nodeId: string) => void;
}) {
  return (
    <article className="nearby-column">
      <header>
        <div>
          <strong>{title}</strong>
          <span>{hint}</span>
        </div>
        <span>{items.length}</span>
      </header>
      {items.length === 0 ? (
        <p className="nearby-empty">{empty}</p>
      ) : (
        <div className="nearby-list">
          {items.slice(0, 5).map((item) => (
            <button type="button" key={item.nodeId} onClick={() => onFocus(item.nodeId)}>
              <span className="nearby-step-type">
                {item.viaStep ? stepType(doc, item.viaStep.step_id) : "node"}
              </span>
              <strong>{nodeLabel(doc, item.nodeId)}</strong>
              <small>{laneIdForRecord(doc, item.nodeId) ? laneLabel(doc, laneIdForRecord(doc, item.nodeId)!) : "unassigned"}</small>
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

function preferredFocusNode(
  doc: RunDocument,
  currentLane: LaneOverview | null,
  lanes: LaneOverview[],
): string | null {
  const current = currentLane ? preferredLaneNode(doc, currentLane) : null;
  if (current) return current;
  for (const lane of lanes.filter((candidate) => candidate.status === "open")) {
    const nodeId = preferredLaneNode(doc, lane);
    if (nodeId) return nodeId;
  }
  return doc.nodes.some((node) => node.node_id === doc.root_node_id) ? doc.root_node_id : doc.nodes[0]?.node_id ?? null;
}

function preferredLaneNode(doc: RunDocument, lane: LaneOverview): string | null {
  const frontiers = sortNodesByRecency(doc, lane.active_frontier_node_ids);
  if (frontiers.length) return frontiers[0];
  if (lane.summary_node_id) return lane.summary_node_id;
  const rank = recordEventRank(doc);
  const group = (doc.groups ?? []).find((candidate) => candidate.kind === "lane" && candidate.lane_id === lane.lane_id);
  return [...(group?.node_ids ?? [])].sort((a, b) => (rank.get(b) ?? -1) - (rank.get(a) ?? -1))[0] ?? null;
}

function sortNodesByRecency(doc: RunDocument, nodeIds: string[]): string[] {
  const rank = recordEventRank(doc);
  return [...nodeIds].sort((a, b) => (rank.get(b) ?? -1) - (rank.get(a) ?? -1));
}

function producerFor(doc: RunDocument, nodeId: string): RunStep | null {
  const rank = recordEventRank(doc);
  return (
    doc.steps
      .filter((step) => step.output_node_id === nodeId)
      .sort((a, b) => {
        if (a.inactive !== b.inactive) return a.inactive ? 1 : -1;
        return (rank.get(b.step_id) ?? -1) - (rank.get(a.step_id) ?? -1);
      })[0] ?? null
  );
}

function primaryPath(doc: RunDocument, nodeId: string): PathPoint[] {
  const reverse: PathPoint[] = [];
  const seen = new Set<string>();
  let current: string | null = nodeId;
  let viaStep: RunStep | null = null;
  while (current && !seen.has(current)) {
    seen.add(current);
    reverse.push({ nodeId: current, viaStep });
    if (current === doc.root_node_id) break;
    const producer = producerFor(doc, current);
    if (!producer || !producer.input_node_ids.length) break;
    viaStep = producer;
    current = producer.input_node_ids[0];
  }
  const path = reverse.reverse();
  return path.map((point, index) => ({
    nodeId: point.nodeId,
    viaStep: index === 0 ? null : producerFor(doc, point.nodeId),
  }));
}

function nearbyNodes(doc: RunDocument, nodeId: string): {
  inputs: NearbyNode[];
  alternatives: NearbyNode[];
  ahead: NearbyNode[];
} {
  const producer = producerFor(doc, nodeId);
  const inputs = (producer?.input_node_ids ?? []).map((inputId) => ({ nodeId: inputId, viaStep: producer }));
  const aheadSteps = doc.steps.filter(
    (step) => !step.inactive && step.input_node_ids.includes(nodeId),
  );
  const ahead = uniqueNearby(aheadSteps.map((step) => ({ nodeId: step.output_node_id, viaStep: step })));
  const alternatives = producer
    ? uniqueNearby(
        doc.steps
          .filter(
            (step) =>
              !step.inactive &&
              step.step_id !== producer.step_id &&
              producer.input_node_ids.some((inputId) => step.input_node_ids.includes(inputId)),
          )
          .map((step) => ({ nodeId: step.output_node_id, viaStep: step })),
      )
    : [];
  return { inputs, alternatives, ahead };
}

function uniqueNearby(items: NearbyNode[]): NearbyNode[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.nodeId)) return false;
    seen.add(item.nodeId);
    return true;
  });
}

function emptyNeighborhood() {
  return { inputs: [] as NearbyNode[], alternatives: [] as NearbyNode[], ahead: [] as NearbyNode[] };
}

function stepsSinceSummary(doc: RunDocument, path: PathPoint[]): number {
  let count = 0;
  for (let index = path.length - 1; index > 0; index -= 1) {
    if (nodeSummaryText(doc, path[index].nodeId)) return count;
    count += 1;
  }
  return count;
}

function positionLabel(inactive: boolean, activeChildren: number): string {
  if (inactive) return "inactive";
  return activeChildren === 0 ? "frontier" : "in history";
}

function attentionType(payload: RunPayload): string {
  const type = payload.type || payload.payload_type;
  return typeof type === "string" ? type.toLowerCase() : "request";
}

function attentionPayloads(doc: RunDocument): RunPayload[] {
  const rank = recordEventRank(doc);
  const inactiveNodes = new Set(doc.nodes.filter((node) => node.inactive).map((node) => node.node_id));
  const inactiveSteps = new Set(doc.steps.filter((step) => step.inactive).map((step) => step.step_id));
  const closedLanes = new Set((doc.lanes ?? []).filter((lane) => lane.status === "closed").map((lane) => lane.lane_id));
  return doc.payloads
    .filter((payload) => {
      if (!ATTENTION_TYPES.has(attentionType(payload))) return false;
      if (payload.target_kind === "node" && inactiveNodes.has(payload.target_id)) return false;
      if (payload.target_kind === "step" && inactiveSteps.has(payload.target_id)) return false;
      const state = payload.content?.status;
      if (typeof state === "string" && RESOLVED_STATES.has(state.toLowerCase())) return false;
      const laneId = laneIdForPayload(doc, payload);
      return !laneId || !closedLanes.has(laneId);
    })
    .sort((a, b) => (rank.get(b.payload_id) ?? -1) - (rank.get(a.payload_id) ?? -1));
}

function laneIdForPayload(doc: RunDocument, payload: RunPayload): string | null {
  return doc.record_provenance?.[payload.payload_id]?.lane_id ?? laneIdForRecord(doc, payload.target_id);
}

function laneNameForPayload(doc: RunDocument, payload: RunPayload): string {
  const laneId = laneIdForPayload(doc, payload);
  return laneId ? laneLabel(doc, laneId) : "unassigned";
}

function frontierSummary(doc: RunDocument, nodeId: string): string {
  const summary = nodeSummaryText(doc, nodeId);
  if (summary) return collapseSummary(summary, 120);
  const producer = producerFor(doc, nodeId);
  if (!producer) return nodeId === doc.root_node_id ? "Run root" : "No description recorded";
  for (const payload of doc.payloads.filter(
    (candidate) => candidate.target_kind === "step" && candidate.target_id === producer.step_id,
  )) {
    const display = payloadDisplayFor(payload, doc);
    if (display.summary) return collapseSummary(display.summary, 120);
    if (display.title && display.title !== "step") return display.title;
  }
  return `${stepType(doc, producer.step_id)} step`;
}

function recentEvents(doc: RunDocument): RunWorkEvent[] {
  return [...(doc.work_events ?? [])]
    .sort((a, b) => {
      const seq = (b.seq ?? -1) - (a.seq ?? -1);
      if (seq) return seq;
      return (b.created_at ?? "").localeCompare(a.created_at ?? "");
    })
    .slice(0, 12);
}

function eventTarget(doc: RunDocument, event: RunWorkEvent): RecordSelection | null {
  const nodes = new Set(doc.nodes.map((node) => node.node_id));
  const steps = new Set(doc.steps.map((step) => step.step_id));
  const candidates = [event.target_id, ...(event.created_records ?? [])].filter(Boolean) as string[];
  for (const id of candidates) {
    if (nodes.has(id)) return { kind: "node", id };
    if (steps.has(id)) return { kind: "step", id };
  }
  return null;
}

function humanize(value: string): string {
  return value.replace(/[._-]+/g, " ");
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}


// Current topic statements — the run's established knowledge, one chip per
// topic (islands badge = unjoined lineages). Clicking opens the topics view.
function TopicsStrip({ doc, onOpenTopics }: { doc: RunDocument; onOpenTopics: () => void }) {
  const topics = listTopics(doc).filter((topic) => topic.summary || topic.islands.length > 0);
  if (!topics.length) return null;
  return (
    <section className="overview-topics" aria-label="Topics">
      <span>topics</span>
      {topics.slice(0, 6).map((topic) => (
        <button key={topic.name} type="button" onClick={onOpenTopics} title={topic.summary?.text ?? ""}>
          <strong>{topic.name}</strong>
          {topic.islands.length > 1 && <em>{topic.islands.length} islands</em>}
        </button>
      ))}
      {topics.length > 6 && <small>+{topics.length - 6} more</small>}
    </section>
  );
}
