// Topics view: flat, name-keyed bundles of meaning, derived from tag /
// topic_summary payloads by topicViews.ts (the mirror of arctx/core/topics.py).
// The list shows each topic's current statement and island count; the detail
// shows the statement, its evidence sources, and the tagged records grouped
// by lineage island — 2+ islands is the "same subject, not yet joined"
// join-candidate signal, not an error.

import { useMemo, useState } from "react";

import { listTopics, type TopicView } from "./topicViews";
import type { RunDocument } from "./types";

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
      {topic && <TopicDetail topic={topic} onSelectRecord={onSelectRecord} />}
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
  topic,
  onSelectRecord,
}: {
  topic: TopicView;
  onSelectRecord: (selection: RecordSelection) => void;
}) {
  const [showHistory, setShowHistory] = useState(false);
  const kinds = new Map(topic.records.map((r) => [r.recordId, r.kind]));
  const notes = new Map(topic.records.map((r) => [r.recordId, r.note]));
  const jump = (recordId: string) =>
    onSelectRecord({ kind: kinds.get(recordId) ?? "node", id: recordId });
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
                sources:
                {topic.summary.sources.map((source) => (
                  <button key={source} type="button" onClick={() => jump(source)}>
                    {source.slice(0, 12)}
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
              {showHistory ? "▾" : "▸"} history ({topic.history.length} statements)
            </button>
            {showHistory &&
              [...topic.history]
                .reverse()
                .slice(1)
                .map((entry) => (
                  <div key={entry.payloadId} className="topics-history-entry">
                    <span>{(entry.createdAt ?? "").slice(0, 16).replace("T", " ") || "–"}</span>
                    <p>{entry.text}</p>
                  </div>
                ))}
          </div>
        )}
      </div>

      {topic.islands.length > 1 && (
        <p className="topics-join-hint">
          {topic.islands.length} unjoined lineages share this topic. Joining is
          one step: <code>arctx add --from {topic.islands[0][0].slice(0, 10)}… --from{" "}
          {topic.islands[1][0].slice(0, 10)}…</code>
        </p>
      )}

      <div className="topics-islands">
        {topic.islands.map((island, index) => (
          <div key={island[0]} className="topics-island">
            <header>island {index + 1}</header>
            {island.map((recordId) => (
              <button key={recordId} type="button" onClick={() => jump(recordId)}>
                <code>{recordId.slice(0, 12)}</code>
                <span className="topics-record-kind">{kinds.get(recordId)}</span>
                {notes.get(recordId) && <span className="topics-record-note">{notes.get(recordId)}</span>}
              </button>
            ))}
          </div>
        ))}
        {topic.inactive.length > 0 && (
          <div className="topics-island topics-island-cut">
            <header>✂ cut</header>
            {topic.inactive.map((recordId) => (
              <button key={recordId} type="button" onClick={() => jump(recordId)}>
                <code>{recordId.slice(0, 12)}</code>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
