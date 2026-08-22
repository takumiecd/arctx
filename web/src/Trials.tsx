// Trials view: derived comparison tables over TrialPayload rows (optimize
// extension). Everything here is computed from the export document by
// trialTables.ts — there is no table record and no server round-trip.

import { useMemo, useState } from "react";

import {
  bestRow,
  deriveTable,
  formatValue,
  sortRows,
  tableNames,
  type TrialColumn,
  type TrialRow,
  type TrialTable,
} from "./trialTables";
import type { RunDocument } from "./types";

type RecordSelection = { kind: "node" | "step"; id: string };

export function Trials({
  doc,
  onSelectRecord,
}: {
  doc: RunDocument;
  onSelectRecord: (selection: RecordSelection) => void;
}) {
  const names = useMemo(() => tableNames(doc), [doc]);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [sort, setSort] = useState<{ column: string; descending: boolean } | null>(null);

  const activeName = selectedName && names.includes(selectedName) ? selectedName : names[0] ?? null;
  const table = useMemo(
    () => (activeName ? deriveTable(doc, activeName) : null),
    [doc, activeName],
  );

  if (!names.length) {
    return (
      <div className="trials-empty">
        <h2>No trial tables yet</h2>
        <p>
          A trial records one scored attempt — the config that was tried and the
          metrics that came out. Tables are born on first use and columns grow
          as trials arrive; nothing is declared up front.
        </p>
        <pre>
          {"arctx ext enable optimize\n"}
          {'arctx trial add --table tile-sweep --col tile=32 --metric latency_ms=1.87'}
        </pre>
      </div>
    );
  }

  const selectTable = (name: string) => {
    setSelectedName(name);
    setSort(null);
  };

  const toggleSort = (column: string) => {
    setSort((prev) =>
      prev && prev.column === column
        ? prev.descending
          ? null
          : { column, descending: true }
        : { column, descending: false },
    );
  };

  return (
    <div className="trials-view">
      <aside className="trials-list">
        <header>
          <strong>Tables</strong>
          <span>{names.length}</span>
        </header>
        {names.map((name) => (
          <TableListEntry
            key={name}
            doc={doc}
            name={name}
            active={name === activeName}
            onSelect={() => selectTable(name)}
          />
        ))}
      </aside>
      {table && (
        <section className="trials-main">
          <TableHeader table={table} sort={sort} onSelectRecord={onSelectRecord} />
          <TableGrid
            table={table}
            sort={sort}
            onToggleSort={toggleSort}
            onSelectRecord={onSelectRecord}
          />
          {table.invalid.length > 0 && (
            <div className="trials-quarantine">
              <strong>⚠ {table.invalid.length} quarantined</strong>
              <p>
                Rows that conflict with the derived schema are kept out of the
                columns instead of corrupting them.
              </p>
              {table.invalid.map(({ row, reason }) => (
                <div key={row.payloadId} className="trials-quarantine-row">
                  <button type="button" onClick={() => onSelectRecord({ kind: "step", id: row.stepId })}>
                    {row.stepId.slice(0, 12)}
                  </button>
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function TableListEntry({
  doc,
  name,
  active,
  onSelect,
}: {
  doc: RunDocument;
  name: string;
  active: boolean;
  onSelect: () => void;
}) {
  const table = useMemo(() => deriveTable(doc, name), [doc, name]);
  const activeRows = table.rows.filter((row) => row.active).length;
  const cutRows = table.rows.length - activeRows;
  return (
    <button
      type="button"
      className={`trials-list-entry${active ? " active" : ""}`}
      onClick={onSelect}
    >
      <strong>{name}</strong>
      <span>
        {activeRows} rows
        {cutRows > 0 && ` (${cutRows} cut)`}
        {table.invalid.length > 0 && ` · ⚠ ${table.invalid.length}`}
      </span>
      <small>{table.columns.map((col) => col.name).join(" · ") || "(no columns)"}</small>
    </button>
  );
}

function TableHeader({
  table,
  sort,
  onSelectRecord,
}: {
  table: TrialTable;
  sort: { column: string; descending: boolean } | null;
  onSelectRecord: (selection: RecordSelection) => void;
}) {
  const sortedColumn = sort
    ? table.columns.find((col) => col.name === sort.column)
    : undefined;
  const showBest = sortedColumn?.section === "metric" && sortedColumn.kind === "number";
  const best = showBest ? bestRow(table, sortedColumn.name, sort?.descending ?? false) : null;
  return (
    <header className="trials-main-header">
      <div>
        <strong>{table.name}</strong>
        <span>
          {table.rows.filter((row) => row.active).length} active rows ·{" "}
          {table.columns.length} columns
        </span>
      </div>
      {best && sortedColumn && (
        <button
          type="button"
          className="trials-best"
          onClick={() => onSelectRecord({ kind: "step", id: best.stepId })}
          title="Jump to this step"
        >
          best ({sort?.descending ? "max" : "min"} {sortedColumn.name} ={" "}
          {formatValue(best.metrics[sortedColumn.name])})
          {best.title ? ` · ${best.title}` : ` · ${best.stepId.slice(0, 10)}`}
        </button>
      )}
    </header>
  );
}

function TableGrid({
  table,
  sort,
  onToggleSort,
  onSelectRecord,
}: {
  table: TrialTable;
  sort: { column: string; descending: boolean } | null;
  onToggleSort: (column: string) => void;
  onSelectRecord: (selection: RecordSelection) => void;
}) {
  const rows = sort ? sortRows(table, sort.column, sort.descending) : table.rows;
  const hasTitle = rows.some((row) => row.title);
  // A row's own id is its payload id; the step is shown only when it groups
  // several rows (a sweep is one Step with N rows, not N Steps).
  const showStep = new Set(table.rows.map((row) => row.stepId)).size !== table.rows.length;
  return (
    <div className="trials-table-scroll">
      <table className="trials-table">
        <thead>
          <tr>
            <th>row</th>
            {showStep && <th>step</th>}
            {hasTitle && <th>title</th>}
            <th>lane</th>
            {table.columns.map((col) => (
              <th
                key={col.name}
                className={`trials-col-${col.section}${sort?.column === col.name ? " sorted" : ""}`}
              >
                <button type="button" onClick={() => onToggleSort(col.name)} title={`${col.section} · ${col.kind}`}>
                  {col.name}
                  {sort?.column === col.name ? (sort.descending ? " ↓" : " ↑") : ""}
                </button>
              </th>
            ))}
            <th>status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <TrialRowView
              key={row.payloadId}
              row={row}
              columns={table.columns}
              hasTitle={hasTitle}
              showStep={showStep}
              onSelectRecord={onSelectRecord}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TrialRowView({
  row,
  columns,
  hasTitle,
  showStep,
  onSelectRecord,
}: {
  row: TrialRow;
  columns: TrialColumn[];
  hasTitle: boolean;
  showStep: boolean;
  onSelectRecord: (selection: RecordSelection) => void;
}) {
  return (
    <tr className={row.active ? "" : "cut"}>
      <td>
        <button
          type="button"
          className="trials-step-link"
          onClick={() => onSelectRecord({ kind: "step", id: row.stepId })}
          title={row.payloadId}
        >
          {row.payloadId.slice(0, 10)}
        </button>
      </td>
      {showStep && (
        <td>
          <button
            type="button"
            className="trials-step-link"
            onClick={() => onSelectRecord({ kind: "step", id: row.stepId })}
            title={row.stepId}
          >
            {row.stepId.slice(0, 10)}
          </button>
        </td>
      )}
      {hasTitle && <td className="trials-title">{row.title ?? "–"}</td>}
      <td className="trials-lane">{row.laneName ?? "–"}</td>
      {columns.map((col) => {
        const source = col.section === "config" ? row.config : row.metrics;
        return (
          <td key={col.name} className={`trials-col-${col.section}`}>
            {formatValue(source[col.name])}
          </td>
        );
      })}
      <td className="trials-status">{row.active ? "active" : "✂ cut"}</td>
    </tr>
  );
}
