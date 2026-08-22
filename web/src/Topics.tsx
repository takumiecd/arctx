// Topics view: flat, name-keyed bundles of meaning, derived from tag /
// topic_summary payloads by topicViews.ts (the mirror of arctx/core/topics.py).
// The list shows each topic's current statement and island count; the detail
// shows the statement, its evidence, and the tagged records as lineage lanes,
// one per island.
//
// Two things the layout is doing on purpose:
//
// - a record reads as the work it stands for (derived label, lane, time), not
//   as an opaque id: an island of ids says nothing about why it is an island.
// - islands are drawn as connected lineages with a dashed gap between them —
//   the gap *is* the message — and the four ways out are offered as commands.
//   A split subject is a candidate, never an error, so nothing here is red.

import { useMemo, useState } from "react";

import { islandStatements, islandTips, listTopics, type TopicRecord, type TopicView } from "./topicViews";
import type { RunDocument } from "./types";

// One hue per island, so the minimap reads as separate constellations rather
// than one speckled cloud. Cycles for topics with many islands.
const ISLAND_COLORS = [
  "var(--color-accent)",
  "var(--color-candidate)",
  "var(--color-success)",
];
const islandColor = (index: number) => ISLAND_COLORS[index % ISLAND_COLORS.length];

type RecordSelection = { kind: "node" | "step"; id: string };

export function Topics({
  doc,
  onSelectRecord,
}: {
  doc: RunDocument;
  onSelectRecord: (selection: RecordSelection) => void;
}) {
  const topics = useMemo(() => listTopics(doc), [doc]);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const activeName =
    selectedName && topics.some((t) => t.name === selectedName)
      ? selectedName
      : topics[0]?.name ?? null;
  const topic = topics.find((t) => t.name === activeName) ?? null;

  if (!topics.length) {
    return (
      <div className="topics-empty">
        <h2>No topics yet</h2>
        <p>
          A topic bundles meaning the way a lane bundles work and a table
          bundles numbers: tag any records into a named subject — connectivity
          is not required — and keep the subject&apos;s current statement.
        </p>
        <pre>
          {"arctx topic tag vectorized-gather n_abc t_def\n"}
          {'arctx topic summarize vectorized-gather --summary "current belief"'}
        </pre>
      </div>
    );
  }

  return (
    <div className="topics-view">
      <aside className="topics-list">
        <header>
          <strong>Topics</strong>
          <span>{topics.length}</span>
        </header>
        {topics.map((candidate) => (
          <TopicListEntry
            key={candidate.name}
            topic={candidate}
            active={candidate.name === activeName}
            onSelect={() => setSelectedName(candidate.name)}
          />
        ))}
      </aside>
      {topic && <TopicDetail doc={doc} topic={topic} onSelectRecord={onSelectRecord} />}
    </div>
  );
}

function TopicListEntry({
  topic,
  active,
  onSelect,
}: {
  topic: TopicView;
  active: boolean;
  onSelect: () => void;
}) {
  const recordCount = topic.islands.reduce((sum, island) => sum + island.length, 0);
  return (
    <button
      type="button"
      className={`topics-list-entry${active ? " active" : ""}`}
      onClick={onSelect}
    >
      <span className="topics-entry-head">
        <strong>{topic.name}</strong>
        {topic.islands.length > 1 && (
          <span className="topics-islands-badge">{topic.islands.length} islands</span>
        )}
      </span>
      <span>
        {recordCount} records
        {topic.inactive.length > 0 && ` (${topic.inactive.length} cut)`}
      </span>
      <small>{topic.summary?.text ?? "(no summary yet)"}</small>
    </button>
  );
}

function TopicDetail({
  doc,
  topic,
  onSelectRecord,
}: {
  doc: RunDocument;
  topic: TopicView;
  onSelectRecord: (selection: RecordSelection) => void;
}) {
  const [showHistory, setShowHistory] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const byId = new Map(topic.records.map((r) => [r.recordId, r]));
  const tips = useMemo(
    () => new Set(topic.islands.flatMap((island) => islandTips(doc, island))),
    [doc, topic],
  );
  const statements = useMemo(() => islandStatements(doc, topic), [doc, topic]);
  const jump = (recordId: string) =>
    onSelectRecord({ kind: byId.get(recordId)?.kind ?? "node", id: recordId });
  return (
    <section className="topics-main">
      <header className="topics-main-header">
        <strong>{topic.name}</strong>
        <span>
          {topic.islands.reduce((sum, island) => sum + island.length, 0)} records ·{" "}
          {topic.islands.length} {topic.islands.length === 1 ? "island" : "islands"}
        </span>
      </header>

      <div className="topics-statement">
        {topic.summary ? (
          <>
            <p>{topic.summary.text}</p>
            {topic.summary.sources.length > 0 && (
              <div className="topics-sources">
                <span>evidence:</span>
                {topic.summary.sources.map((source) => (
                  <button key={source} type="button" onClick={() => jump(source)}>
                    <span className="topics-source-kind">
                      {byId.get(source)?.kind ?? "record"}
                    </span>
                    {byId.get(source)?.label ?? source.slice(0, 12)}
                  </button>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="topics-no-statement">
            No statement yet — <code>arctx topic summarize {topic.name} --summary …</code>
          </p>
        )}
        {topic.history.length > 1 && (
          <div className="topics-history">
            <button type="button" onClick={() => setShowHistory((prev) => !prev)}>
              {showHistory ? "▾" : "▸"} how the belief changed ({topic.history.length}{" "}
              statements)
            </button>
            {/* Statements get rewritten wholesale, so a word-level diff would
                mark almost everything as changed. What carries the signal is
                the evidence each version leaned on. */}
            {showHistory &&
              [...topic.history]
                .reverse()
                .slice(1)
                .map((entry) => (
                  <div key={entry.payloadId} className="topics-history-entry">
                    <span>
                      {(entry.createdAt ?? "").slice(0, 16).replace("T", " ") || "–"}
                      {entry.userId ? ` · ${entry.userId}` : ""}
                    </span>
                    <div>
                      <p>{entry.text}</p>
                      {entry.sources.length > 0 && (
                        <div className="topics-sources">
                          <span>evidence:</span>
                          {entry.sources.map((source) => (
                            <button key={source} type="button" onClick={() => jump(source)}>
                              {byId.get(source)?.label ?? source.slice(0, 12)}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
          </div>
        )}
      </div>

      {topic.islands.length > 1 && (
        <SplitResolutions doc={doc} topic={topic} />
      )}

      <div className="topics-islands">
        {topic.islands.map((island, index) => (
          <div key={island[0]} className="topics-island">
            {index > 0 && <span className="topics-island-gap" aria-hidden="true" />}
            <header>
              <b style={{ color: islandColor(index) }}>island {index + 1}</b>
              <span>{island.length} records</span>
            </header>
            {/* What this lineage concluded. Two islands is a shape; the
                contradiction to settle lives in the two statements. */}
            <p className="topics-island-says">
              {statements.perIsland[index]?.text ?? "この系譜だけの結論はまだ無い"}
            </p>
            <div className="topics-lineage">
              {island.map((recordId) => (
                <RecordCard
                  key={recordId}
                  record={byId.get(recordId)}
                  recordId={recordId}
                  tip={tips.has(recordId)}
                  onSelect={jump}
                  onHover={setHovered}
                />
              ))}
            </div>
          </div>
        ))}
        {topic.inactive.length > 0 && (
          <div className="topics-island topics-island-cut">
            <header>
              <b>✂ cut</b>
              <span>out of every island</span>
            </header>
            <div className="topics-lineage">
              {topic.inactive.map((recordId) => (
                <RecordCard
                  key={recordId}
                  record={byId.get(recordId)}
                  recordId={recordId}
                  onSelect={jump}
                  onHover={setHovered}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <TopicMinimap doc={doc} topic={topic} hovered={hovered} onSelect={jump} />
    </section>
  );
}

// A tagged record, read as the work it stands for. The tip of an island is
// marked because that is what a join takes as its input.
function RecordCard({
  record,
  recordId,
  tip = false,
  onSelect,
  onHover,
}: {
  record: TopicRecord | undefined;
  recordId: string;
  tip?: boolean;
  onSelect: (recordId: string) => void;
  onHover?: (recordId: string | null) => void;
}) {
  const classes = ["topics-record"];
  if (tip) classes.push("tip");
  if (record && !record.active) classes.push("cut");
  return (
    <button
      type="button"
      className={classes.join(" ")}
      onClick={() => onSelect(recordId)}
      onMouseEnter={() => onHover?.(recordId)}
      onMouseLeave={() => onHover?.(null)}
      onFocus={() => onHover?.(recordId)}
      onBlur={() => onHover?.(null)}
    >
      <span className={`topics-record-glyph ${record?.kind ?? "node"}`}>
        {record?.kind === "step" ? "→" : "●"}
      </span>
      <span className="topics-record-body">
        <span className="topics-record-title">{record?.label ?? recordId.slice(0, 12)}</span>
        <span className="topics-record-sub">
          {record?.laneName && <span className="topics-lane-chip">{record.laneName}</span>}
          <span title={recordId}>{recordId.slice(0, 10)}</span>
          {record?.createdAt && <span>{record.createdAt.slice(0, 16).replace("T", " ")}</span>}
          {tip && <span className="topics-tip-flag">tip</span>}
        </span>
        {record?.note && <span className="topics-record-note">{record.note}</span>}
      </span>
    </button>
  );
}

// Where the subject sits in the run. Not the graph's own geometry — a run
// with 78 lanes collapses into a hairline at strip size — but the two axes a
// reader actually thinks in: which lane, and when. Each row is a lane that
// carries this topic; faint ticks are that lane's other records, so a lit dot
// reads as "here, among all this". Islands keep their colour, so a subject
// split across lanes shows as separate constellations.
function TopicMinimap({
  doc,
  topic,
  hovered,
  onSelect,
}: {
  doc: RunDocument;
  topic: TopicView;
  hovered: string | null;
  onSelect: (recordId: string) => void;
}) {
  const rows = useMemo(() => {
    const provenance = doc.record_provenance ?? {};
    const entries = Object.entries(provenance)
      .map(([recordId, p]) => ({
        recordId,
        lane: p.lane_name ?? p.lane_id ?? "(no lane)",
        at: p.created_at ?? "",
      }))
      .sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
    const order = new Map(entries.map((entry, index) => [entry.recordId, index]));

    const island = new Map<string, number>();
    topic.islands.forEach((members, index) => {
      for (const recordId of members) island.set(recordId, index);
    });

    const laneOf = new Map(entries.map((entry) => [entry.recordId, entry.lane]));
    const laneNames: string[] = [];
    for (const recordId of island.keys()) {
      const lane = laneOf.get(recordId);
      if (lane && !laneNames.includes(lane)) laneNames.push(lane);
    }

    return {
      total: entries.length || 1,
      island,
      order,
      lanes: laneNames.map((lane) => {
        // A lane's work happens in a burst, so its records compress to a few
        // pixels of the run's timeline. Draw the burst as the lane's active
        // window rather than as ticks nothing can tell apart.
        const indices = entries
          .filter((entry) => entry.lane === lane)
          .map((entry) => order.get(entry.recordId)!);
        return {
          lane,
          span: indices.length
            ? { from: Math.min(...indices), to: Math.max(...indices), count: indices.length }
            : null,
          lit: [...island.keys()].filter((recordId) => laneOf.get(recordId) === lane),
        };
      }),
    };
  }, [doc, topic]);

  if (!rows.lanes.length) return null;

  const ROW = 22;
  const LABEL = 150;
  const WIDTH = 1000;
  const height = rows.lanes.length * ROW;
  const x = (index: number) => LABEL + (index / rows.total) * (WIDTH - LABEL - 12);

  return (
    <figure className="topics-map">
      <figcaption>
        どの lane に・いつ散っているか · {rows.island.size} records / {rows.lanes.length} lanes
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ maxHeight: `${height}px` }}
        role="img"
        aria-label={`${topic.name} のタグ済み record が run のどの lane のどのあたりにあるか`}
      >
        {rows.lanes.map((row, index) => {
          const y = index * ROW + ROW / 2;
          return (
            <g key={row.lane}>
              <text className="topics-map-lane" x={LABEL - 10} y={y + 4} textAnchor="end">
                {row.lane}
              </text>
              <line className="topics-map-rule" x1={LABEL} y1={y} x2={WIDTH - 12} y2={y} />
              {row.span && (
                <line
                  className="topics-map-span"
                  x1={x(row.span.from) - 3}
                  y1={y}
                  x2={x(row.span.to) + 3}
                  y2={y}
                >
                  <title>{`${row.lane}: ${row.span.count} records`}</title>
                </line>
              )}
              {row.lit.map((recordId) => (
                <circle
                  key={recordId}
                  className="topics-map-lit"
                  cx={x(rows.order.get(recordId) ?? 0)}
                  cy={y}
                  r={hovered === recordId ? 9 : 6}
                  fill={islandColor(rows.island.get(recordId) ?? 0)}
                  onClick={() => onSelect(recordId)}
                >
                  <title>{recordId}</title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

// A split subject has exactly four causes, and each one is a command. The
// same four the CLI prints — a candidate, never an error, so nothing is red
// and nothing here blocks.
function SplitResolutions({ doc, topic }: { doc: RunDocument; topic: TopicView }) {
  const [copied, setCopied] = useState<string | null>(null);
  const tips = topic.islands.map((island) => islandTips(doc, island)[0] ?? island[0]);
  const last = tips[tips.length - 1];
  // When the current statement already cites two or more islands, the subject
  // was settled in prose and only the graph lags behind — join can reuse it.
  const { reconciling } = islandStatements(doc, topic);
  const joinCommand = reconciling
    ? `arctx topic join ${topic.name}`
    : `arctx topic join ${topic.name} --summary "..."`;
  const copy = (command: string) => {
    setCopied(command);
    void navigator.clipboard?.writeText(command).catch(() => undefined);
    window.setTimeout(() => setCopied(null), 1400);
  };
  const options: { when: string; command: string }[] = [
    {
      when: reconciling
        ? "現在の主張は既に両方を引いている（結論を再利用）"
        : "both are right, under different conditions",
      command: joinCommand,
    },
    {
      when: "they turned out to be two subjects",
      command: `arctx topic split ${topic.name} --island ${topic.islands.length} --into NEW_NAME --summary "..."`,
    },
    { when: `island ${topic.islands.length} was a dead end`, command: `arctx cut ${last}` },
    { when: "the tag was a mistake", command: `arctx topic untag ${topic.name} ${last}` },
  ];
  return (
    <div className="topics-split">
      <p className="topics-split-head">
        <strong>{topic.islands.length} lineages</strong> carry this topic without meeting.
        A candidate, not an error — four ways out:
      </p>
      <ul>
        {options.map((option) => (
          <li key={option.command}>
            <span>{option.when}</span>
            <code>{option.command}</code>
            <button type="button" onClick={() => copy(option.command)}>
              {copied === option.command ? "copied" : "copy"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
