// Derived trial tables — the TypeScript mirror of
// arctx/ext/optimize/tables.py. Keep the two in sync.
//
// There is no table record. A "table" is a name shared by trial rows; the
// columns, each column's value kind, and the best row are all derived from
// the rows at read time. The schema is built from active rows in record
// order — the first active row to use a key fixes its section and kind.
// Active rows that conflict are quarantined; cut rows are displayed but
// never shape the schema.

import { isTrialPayload, type RunDocument } from "./types";

export type ValueKind = "number" | "bool" | "str";
export type Section = "config" | "metric";

export interface TrialColumn {
  name: string;
  section: Section;
  kind: ValueKind;
  firstStepId: string;
}

export interface TrialRow {
  stepId: string;
  payloadId: string;
  title: string | null;
  tables: string[];
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
  active: boolean;
  laneName: string | null;
}

export interface TrialTable {
  name: string;
  columns: TrialColumn[];
  rows: TrialRow[];
  invalid: { row: TrialRow; reason: string }[];
}

export function valueKind(value: unknown): ValueKind | null {
  if (typeof value === "boolean") return "bool";
  if (typeof value === "number") return "number";
  if (typeof value === "string") return "str";
  return null;
}

export function trialRows(doc: RunDocument): TrialRow[] {
  const inactiveSteps = new Set(
    doc.steps.filter((step) => step.inactive).map((step) => step.step_id),
  );
  const rows: TrialRow[] = [];
  for (const payload of doc.payloads) {
    if (!isTrialPayload(payload)) continue;
    const stepId = payload.target_id;
    const provenance = doc.record_provenance?.[stepId];
    rows.push({
      stepId,
      payloadId: payload.payload_id,
      title: payload.title ?? null,
      tables: payload.tables ?? [],
      config: payload.config ?? {},
      metrics: payload.metrics ?? {},
      active: !inactiveSteps.has(stepId),
      laneName: provenance?.lane_name ?? null,
    });
  }
  return rows;
}

function rowItems(row: TrialRow): [Section, string, unknown][] {
  const items: [Section, string, unknown][] = [];
  for (const [key, value] of Object.entries(row.config)) items.push(["config", key, value]);
  for (const [key, value] of Object.entries(row.metrics)) items.push(["metric", key, value]);
  return items;
}

function checkRow(row: TrialRow, schema: Map<string, TrialColumn>): string | null {
  for (const [section, key, value] of rowItems(row)) {
    const kind = valueKind(value);
    if (kind === null) return `value for "${key}" must be a scalar (number / bool / string)`;
    const column = schema.get(key);
    if (!column) continue;
    if (column.section !== section) {
      return `"${key}" is a ${column.section} column (first set by ${column.firstStepId})`;
    }
    if (column.kind !== kind) {
      return `"${key}" is ${column.kind} (first set by ${column.firstStepId}), got ${JSON.stringify(value)} (${kind})`;
    }
  }
  const dup = Object.keys(row.config).find((key) => key in row.metrics);
  if (dup) return `"${dup}" appears in both config and metrics`;
  return null;
}

function extendSchema(row: TrialRow, schema: Map<string, TrialColumn>): void {
  for (const [section, key, value] of rowItems(row)) {
    if (schema.has(key)) continue;
    const kind = valueKind(value);
    if (kind === null) continue;
    schema.set(key, { name: key, section, kind, firstStepId: row.stepId });
  }
}

export function deriveTable(doc: RunDocument, name: string): TrialTable {
  const rows = trialRows(doc).filter((row) => row.tables.includes(name));
  const schema = new Map<string, TrialColumn>();
  const invalid: { row: TrialRow; reason: string }[] = [];
  const kept: TrialRow[] = [];
  for (const row of rows) {
    if (!row.active) {
      kept.push(row);
      continue;
    }
    const reason = checkRow(row, schema);
    if (reason !== null) {
      invalid.push({ row, reason });
      continue;
    }
    extendSchema(row, schema);
    kept.push(row);
  }
  // Config columns first, then metrics; first-seen order within each (Map
  // iteration order is insertion order, and sort is stable).
  const columns = [...schema.values()].sort(
    (a, b) => (a.section === "config" ? 0 : 1) - (b.section === "config" ? 0 : 1),
  );
  return { name, columns, rows: kept, invalid };
}

export function tableNames(doc: RunDocument): string[] {
  const seen: string[] = [];
  for (const row of trialRows(doc)) {
    for (const name of row.tables) {
      if (!seen.includes(name)) seen.push(name);
    }
  }
  return seen;
}

export function listTables(doc: RunDocument): TrialTable[] {
  return tableNames(doc).map((name) => deriveTable(doc, name));
}

export function bestRow(
  table: TrialTable,
  metric: string,
  maximize: boolean,
): TrialRow | null {
  const candidates = table.rows.filter(
    (row) => row.active && valueKind(row.metrics[metric]) === "number",
  );
  if (!candidates.length) return null;
  return candidates.reduce((best, row) => {
    const a = best.metrics[metric] as number;
    const b = row.metrics[metric] as number;
    return (maximize ? b > a : b < a) ? row : best;
  });
}

export function sortRows(
  table: TrialTable,
  column: string,
  descending: boolean,
): TrialRow[] {
  const valueOf = (row: TrialRow): unknown =>
    column in row.metrics ? row.metrics[column] : row.config[column];
  const present = table.rows.filter((row) => valueOf(row) != null);
  const absent = table.rows.filter((row) => valueOf(row) == null);
  const rank = (value: unknown): [number, number | string] => {
    if (typeof value === "boolean") return [1, value ? 1 : 0];
    if (typeof value === "number") return [0, value];
    return [2, String(value)];
  };
  present.sort((a, b) => {
    const [groupA, keyA] = rank(valueOf(a));
    const [groupB, keyB] = rank(valueOf(b));
    if (groupA !== groupB) return groupA - groupB;
    const cmp = keyA < keyB ? -1 : keyA > keyB ? 1 : 0;
    return descending ? -cmp : cmp;
  });
  return [...present, ...absent];
}

export function formatValue(value: unknown): string {
  if (value == null) return "–";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(6)));
  }
  return String(value);
}
