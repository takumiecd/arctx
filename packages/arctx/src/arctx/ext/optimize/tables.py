"""Derived trial tables.

There is no table record. A "table" is a name shared by TrialPayload rows,
the same way a lane is a flat name shared by its steps. Everything a reader
looks at — which tables exist, their columns, each column's value kind, the
best row — is derived from the rows at read time.

Schema discipline is split between write and read:

- ``validate_trial`` runs at write time: a new column name grows the table
  freely (with a notice), but a column's value kind (number / bool / str) is
  fixed by the first active row that used it, and a name cannot be a config
  column in one row and a metric column in another. Type conflicts are
  rejected before anything is written.
- Reading stays tolerant: rows written past the CLI that conflict with the
  derived schema are quarantined (returned in ``TrialTable.invalid``) instead
  of corrupting the column layout. Records are never dropped silently.

Cut rows keep their place in the display but leave the schema: cutting a
step is the append-only eraser for a mistyped first row — the column's kind
is freed for the next writer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from arctx.core.cuts import inactive_step_ids
from arctx.core.lanes import lane_membership
from arctx.core.run_graph import RunGraph
from arctx.core.types import JSONValue
from arctx.ext.optimize.payloads import TrialPayload

SECTION_CONFIG = "config"
SECTION_METRIC = "metric"


def value_kind(value: JSONValue) -> str | None:
    """Classify a trial value: "number", "bool", "str", or None if non-scalar.

    bool is checked before number because bool is an int subclass in Python.
    int and float deliberately collapse into one "number" kind — what must
    stay stable for sorting and best-row selection is numericness, not width.
    """
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "str"
    return None


@dataclass(frozen=True)
class TrialColumn:
    name: str
    section: str  # SECTION_CONFIG | SECTION_METRIC
    kind: str  # "number" | "bool" | "str"
    first_step_id: str  # the active row that fixed this column's kind


@dataclass(frozen=True)
class TrialRow:
    step_id: str
    payload_id: str
    title: str | None
    tables: tuple[str, ...]
    config: dict[str, JSONValue]
    metrics: dict[str, JSONValue]
    active: bool
    lane_name: str | None


@dataclass(frozen=True)
class TrialTable:
    name: str
    columns: tuple[TrialColumn, ...]  # config columns first, then metrics
    rows: tuple[TrialRow, ...]  # active + cut, record order
    invalid: tuple[tuple[TrialRow, str], ...]  # quarantined active rows

    @property
    def active_rows(self) -> tuple[TrialRow, ...]:
        return tuple(row for row in self.rows if row.active)


def trial_rows(graph: RunGraph) -> list[TrialRow]:
    """All trial rows in the run, in record (append) order."""
    inactive = inactive_step_ids(graph)
    membership = lane_membership(graph)
    rows: list[TrialRow] = []
    for payload in graph.payloads.values():
        if not isinstance(payload, TrialPayload):
            continue
        step_id = payload.target_id
        lane_id = membership.step_to_lane.get(step_id)
        lane = graph.lanes.get(lane_id) if lane_id else None
        rows.append(
            TrialRow(
                step_id=step_id,
                payload_id=payload.payload_id,
                title=payload.title,
                tables=payload.tables,
                config=dict(payload.config),
                metrics=dict(payload.metrics),
                active=step_id not in inactive,
                lane_name=lane.name if lane is not None else None,
            )
        )
    return rows


def _row_items(row: TrialRow) -> list[tuple[str, str, JSONValue]]:
    """(section, key, value) triples for a row, config first."""
    items = [(SECTION_CONFIG, key, value) for key, value in row.config.items()]
    items += [(SECTION_METRIC, key, value) for key, value in row.metrics.items()]
    return items


def _check_row(
    row: TrialRow, schema: dict[str, TrialColumn]
) -> str | None:
    """Reason this row conflicts with *schema*, or None if it fits."""
    for section, key, value in _row_items(row):
        kind = value_kind(value)
        if kind is None:
            return f'value for "{key}" must be a scalar (number / bool / string)'
        column = schema.get(key)
        if column is None:
            continue
        if column.section != section:
            return (
                f'"{key}" is a {column.section} column '
                f"(first set by {column.first_step_id})"
            )
        if column.kind != kind:
            return (
                f'"{key}" is {column.kind} '
                f"(first set by {column.first_step_id}), got {value!r} ({kind})"
            )
    if set(row.config) & set(row.metrics):
        dup = sorted(set(row.config) & set(row.metrics))[0]
        return f'"{dup}" appears in both config and metrics'
    return None


def _extend_schema(row: TrialRow, schema: dict[str, TrialColumn]) -> None:
    for section, key, value in _row_items(row):
        if key in schema:
            continue
        kind = value_kind(value)
        if kind is None:
            continue
        schema[key] = TrialColumn(
            name=key, section=section, kind=kind, first_step_id=row.step_id
        )


def derive_table(graph: RunGraph, name: str) -> TrialTable:
    """Derive one table from the rows that carry *name*.

    The schema is built from active rows in record order — the first active
    row to use a key fixes its section and kind. Active rows that conflict
    are quarantined; cut rows are displayed but never shape the schema.
    """
    rows = [row for row in trial_rows(graph) if name in row.tables]
    schema: dict[str, TrialColumn] = {}
    invalid: list[tuple[TrialRow, str]] = []
    kept: list[TrialRow] = []
    for row in rows:
        if not row.active:
            kept.append(row)
            continue
        reason = _check_row(row, schema)
        if reason is not None:
            invalid.append((row, reason))
            continue
        _extend_schema(row, schema)
        kept.append(row)
    columns = tuple(
        sorted(
            schema.values(),
            key=lambda col: (0 if col.section == SECTION_CONFIG else 1,),
        )
    )
    return TrialTable(
        name=name, columns=columns, rows=tuple(kept), invalid=tuple(invalid)
    )


def table_names(graph: RunGraph) -> list[str]:
    """Table names in first-appearance order."""
    seen: list[str] = []
    for row in trial_rows(graph):
        for name in row.tables:
            if name not in seen:
                seen.append(name)
    return seen


def list_tables(graph: RunGraph) -> list[TrialTable]:
    return [derive_table(graph, name) for name in table_names(graph)]


def validate_trial(
    graph: RunGraph,
    *,
    tables: Iterable[str],
    config: dict[str, JSONValue],
    metrics: dict[str, JSONValue],
) -> tuple[list[str], list[str]]:
    """Write-time check of a prospective trial against every listed table.

    Returns ``(errors, notices)``. Errors block the write (type or section
    conflicts, non-scalar values). Notices report implicit growth: a table
    springing into existence, or a new column joining an existing table.
    """
    errors: list[str] = []
    notices: list[str] = []
    candidate = TrialRow(
        step_id="(new)",
        payload_id="(new)",
        title=None,
        tables=tuple(tables),
        config=dict(config),
        metrics=dict(metrics),
        active=True,
        lane_name=None,
    )
    for name in candidate.tables:
        table = derive_table(graph, name)
        schema = {col.name: col for col in table.columns}
        reason = _check_row(candidate, schema)
        if reason is not None:
            errors.append(f'table "{name}": {reason}')
            continue
        if not table.active_rows:
            column_names = [key for _, key, _ in _row_items(candidate)]
            notices.append(
                f'new table "{name}" (columns: {", ".join(column_names)})'
            )
            continue
        for _, key, _ in _row_items(candidate):
            if key not in schema:
                notices.append(f'new column "{key}" in table "{name}"')
    return errors, notices


def best_row(
    table: TrialTable, metric: str, *, maximize: bool = False
) -> TrialRow | None:
    """The active row with the smallest (or largest) value for *metric*."""
    candidates = [
        row for row in table.active_rows if value_kind(row.metrics.get(metric)) == "number"
    ]
    if not candidates:
        return None
    return (max if maximize else min)(candidates, key=lambda row: row.metrics[metric])


def sort_rows(
    table: TrialTable, column: str, *, descending: bool = False
) -> tuple[TrialRow, ...]:
    """Rows sorted by *column* (config or metric); rows missing it sort last."""

    def value_of(row: TrialRow):
        if column in row.metrics:
            return row.metrics[column]
        return row.config.get(column)

    def key(row: TrialRow):
        value = value_of(row)
        if isinstance(value, bool):
            return (1, int(value))
        if isinstance(value, (int, float)):
            return (0, value)
        return (2, str(value))

    present = [row for row in table.rows if value_of(row) is not None]
    absent = [row for row in table.rows if value_of(row) is None]
    present.sort(key=key, reverse=descending)
    return tuple(present + absent)


__all__ = [
    "TrialColumn",
    "TrialRow",
    "TrialTable",
    "best_row",
    "derive_table",
    "list_tables",
    "sort_rows",
    "table_names",
    "trial_rows",
    "validate_trial",
    "value_kind",
]
