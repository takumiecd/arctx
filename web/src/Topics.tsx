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

import { islandTips, listTopics, type TopicRecord, type TopicView } from "./topicViews";
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
  const byId = new Map(topic.records.map((r) => [r.recordId, r]));
  const tips = useMemo(
    () => new Set(topic.islands.flatMap((island) => islandTips(doc, island))),
    [doc, topic],
  );
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
              <b>island {index + 1}</b>
              <span>{island.length} records</span>
            </header>
            <div className="topics-lineage">
              {island.map((recordId) => (
                <RecordCard
                  key={recordId}
                  record={byId.get(recordId)}
                  recordId={recordId}
                  tip={tips.has(recordId)}
                  onSelect={jump}
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
                />
              ))}
            </div>
          </div>
        )}
      </div>
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
}: {
  record: TopicRecord | undefined;
  recordId: string;
  tip?: boolean;
  onSelect: (recordId: string) => void;
}) {
  const classes = ["topics-record"];
  if (tip) classes.push("tip");
  if (record && !record.active) classes.push("cut");
  return (
    <button type="button" className={classes.join(" ")} onClick={() => onSelect(recordId)}>
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

// A split subject has exactly four causes, and each one is a command. The
// same four the CLI prints — a candidate, never an error, so nothing is red
// and nothing here blocks.
function SplitResolutions({ doc, topic }: { doc: RunDocument; topic: TopicView }) {
  const [copied, setCopied] = useState<string | null>(null);
  const tips = topic.islands.map((island) => islandTips(doc, island)[0] ?? island[0]);
  const last = tips[tips.length - 1];
  const joinCommand = `arctx topic join ${topic.name} --summary "..."`;
  const copy = (command: string) => {
    setCopied(command);
    void navigator.clipboard?.writeText(command).catch(() => undefined);
    window.setTimeout(() => setCopied(null), 1400);
  };
  const options: { when: string; command: string }[] = [
    { when: "both are right, under different conditions", command: joinCommand },
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
