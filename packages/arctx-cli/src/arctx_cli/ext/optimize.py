"""CLI for the optimize extension: ``arctx trial`` and ``arctx trials``.

``trial add`` mirrors ``arctx add`` (one Step from input nodes, defaulting to
the current lane's single active frontier) but writes a typed TrialPayload and
validates it against the derived schema of every listed table before anything
is written: new columns grow a table with a notice, type conflicts are errors.

``trials`` is read-only: with no argument it lists every table with its
columns; with a table name it prints the derived comparison table.
"""

from __future__ import annotations

import argparse
import json
import sys

import arctx.ext.optimize.payloads  # noqa: F401  (registers the trial decoder)
from arctx.ext.optimize import tables as trial_tables
from arctx.ext.optimize.payloads import TrialPayload

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.commands._targets import step_view
from arctx_cli.commands.add import _default_input_node_ids
from arctx_cli.context import (
    resolve_lane_id_from_args,
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
)
from arctx_cli.lane_gate import ensure_lane_open
from arctx_cli.post_write_check import warn_if_invalid

# ---------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------


def _parse_scalar(text: str):
    """Parse a CLI value: JSON scalar when possible, bare string otherwise."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return text
    if value is None or isinstance(value, (dict, list)):
        raise ValueError(
            f"value must be a scalar (number / bool / string), got {text!r}"
        )
    return value


def _parse_kv(pairs: list[str] | None, flag: str) -> dict:
    out: dict = {}
    for item in pairs or []:
        key, sep, raw = item.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ValueError(f"{flag} expects KEY=VALUE, got {item!r}")
        out[key] = _parse_scalar(raw)
    return out


def _parse_best(spec: str) -> tuple[str, bool]:
    """Parse ``min:COL`` / ``max:COL`` / bare ``COL`` (= min) into (col, maximize)."""
    direction, sep, column = spec.partition(":")
    if not sep:
        return spec, False
    if direction not in ("min", "max"):
        raise ValueError(f"--best expects min:COL or max:COL, got {spec!r}")
    return column, direction == "max"


# ---------------------------------------------------------------------------
# trial add
# ---------------------------------------------------------------------------


def add_trial_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("trial", help="Record scored trials")
    sub = parser.add_subparsers(dest="trial_command", required=True)

    add = sub.add_parser(
        "add",
        help="Add one trial Step (config + metrics) to one or more tables",
    )
    add.add_argument(
        "--table",
        action="append",
        required=True,
        dest="tables",
        metavar="NAME",
        help="Table this trial belongs to (repeatable). First use creates the table.",
    )
    add.add_argument(
        "--col",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help="Config value that was tried (repeatable)",
    )
    add.add_argument(
        "--metric",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help="Measured result (repeatable, at least one)",
    )
    add.add_argument(
        "--from",
        action="append",
        default=None,
        dest="input_nodes",
        metavar="NODE_ID",
        help=(
            "Input node (repeatable). If omitted, defaults to the current "
            "lane's single active frontier node."
        ),
    )
    add.add_argument("--title", default=None)
    add.add_argument("--run", default=None)
    add.add_argument("--store-dir", default=None)
    add.add_argument("--user", default=None)
    add.add_argument("--lane", default=None)
    add.add_argument(
        "--force", action="store_true", help="Write even if the target lane is closed"
    )
    return parser


def run_trial_add_command(
    *,
    run_id: str,
    tables: list[str],
    config: dict,
    metrics: dict,
    input_node_ids: list[str] | None,
    title: str | None,
    store_dir: str | None,
    user_id: str | None = None,
    lane_id: str | None = None,
    force: bool = False,
) -> dict:
    if not metrics:
        raise ValueError(
            "a trial needs at least one --metric KEY=VALUE (record results, "
            "not intentions — use `arctx add` for unscored steps)"
        )
    table_names = [name.strip() for name in tables]
    if any(not name for name in table_names):
        raise ValueError("--table NAME cannot be empty")

    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    ensure_lane_open(handle, lane_id, force=force)
    if not input_node_ids:
        input_node_ids = _default_input_node_ids(handle, lane_id or "default")

    errors, notices = trial_tables.validate_trial(
        handle.run_graph, tables=table_names, config=config, metrics=metrics
    )
    if errors:
        raise ValueError("\n".join(errors))

    payload = TrialPayload(
        payload_id="pending",
        target_id="pending",
        tables=tuple(table_names),
        config=config,
        metrics=metrics,
        title=title,
    )
    before = graph_counts(handle)
    step = handle.add_step(
        input_node_ids,
        payload,
        user_id=user_id,
        lane_id=lane_id,
    )
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane_id,
        before=before,
    )
    return {"step": step_view(step), "notices": notices}


def cli_trial(args) -> int:
    try:
        if args.trial_command != "add":
            raise ValueError(f"unknown trial command: {args.trial_command!r}")
        run_id = resolve_run_id_from_args(args)
        result = run_trial_add_command(
            run_id=run_id,
            tables=args.tables,
            config=_parse_kv(args.col, "--col"),
            metrics=_parse_kv(args.metric, "--metric"),
            input_node_ids=args.input_nodes,
            title=args.title,
            store_dir=args.store_dir,
            user_id=resolve_user_id_from_args(args),
            lane_id=resolve_lane_id_from_args(args),
            force=args.force,
        )
        for notice in result["notices"]:
            print(f"notice: {notice}")
        print(json.dumps(result["step"], ensure_ascii=False, indent=2))
        strict_rc = warn_if_invalid(run_id, args.store_dir, command_name="trial add")
        return strict_rc or 0
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# trials (read-only)
# ---------------------------------------------------------------------------


def add_trials_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "trials",
        help="List trial tables, or print one table",
    )
    parser.add_argument(
        "name",
        nargs="?",
        default=None,
        metavar="TABLE",
        help="Table name. Omit to list every table with its columns.",
    )
    parser.add_argument("--sort", default=None, metavar="COL", help="Sort rows by a column")
    parser.add_argument("--desc", action="store_true", help="Sort descending")
    parser.add_argument(
        "--best",
        default=None,
        metavar="[min:|max:]COL",
        help="Print only the best active row for a metric (default min)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    return parser


def _row_dict(row: trial_tables.TrialRow) -> dict:
    return {
        "step_id": row.step_id,
        "payload_id": row.payload_id,
        "title": row.title,
        "tables": list(row.tables),
        "config": dict(row.config),
        "metrics": dict(row.metrics),
        "active": row.active,
        "lane": row.lane_name,
    }


def _table_dict(table: trial_tables.TrialTable) -> dict:
    return {
        "name": table.name,
        "columns": [
            {"name": col.name, "section": col.section, "kind": col.kind}
            for col in table.columns
        ],
        "rows": [_row_dict(row) for row in table.rows],
        "invalid": [
            {"row": _row_dict(row), "reason": reason} for row, reason in table.invalid
        ],
    }


def _load_graph(run_id: str, store_dir: str | None):
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    return store.load_run(run_id).run_graph


def run_trials_command(
    *,
    run_id: str,
    name: str | None,
    store_dir: str | None,
) -> dict:
    graph = _load_graph(run_id, store_dir)
    if name is None:
        return {"tables": [_table_dict(t) for t in trial_tables.list_tables(graph)]}
    names = trial_tables.table_names(graph)
    if name not in names:
        known = ", ".join(names) if names else "(none yet)"
        raise KeyError(f"unknown table: {name!r}. Tables in this run: {known}")
    return {"table": _table_dict(trial_tables.derive_table(graph, name))}


def _format_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _print_aligned(rows: list[list[str]]) -> None:
    if not rows:
        return
    widths = [max(len(line[i]) for line in rows) for i in range(len(rows[0]))]
    for line in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip())


def _print_table(table: trial_tables.TrialTable, *, sort: str | None, desc: bool) -> None:
    rows = trial_tables.sort_rows(table, sort, descending=desc) if sort else table.rows
    has_title = any(row.title for row in rows)
    header = ["step"]
    if has_title:
        header.append("title")
    header += ["lane"]
    header += [col.name for col in table.columns]
    header += ["status"]
    lines = [header]
    for row in rows:
        line = [row.step_id[:10]]
        if has_title:
            line.append(row.title or "-")
        line.append(row.lane_name or "-")
        for col in table.columns:
            source = row.config if col.section == trial_tables.SECTION_CONFIG else row.metrics
            line.append(_format_value(source.get(col.name)))
        line.append("active" if row.active else "✂ cut")
        lines.append(line)
    _print_aligned(lines)
    if table.invalid:
        print()
        for row, reason in table.invalid:
            print(f"⚠ {row.step_id[:10]} quarantined: {reason}")


def _print_overview(tables: list[trial_tables.TrialTable]) -> None:
    if not tables:
        print("no trial tables in this run. Record one with:")
        print("  arctx trial add --table NAME --col k=v --metric k=v")
        return
    for table in tables:
        active = len(table.active_rows)
        cut = len(table.rows) - active
        counts = f"{active} rows" + (f" ({cut} cut)" if cut else "")
        columns = ", ".join(f"{col.name}:{col.kind}" for col in table.columns)
        print(f"{table.name}  ·  {counts}  ·  columns: {columns or '(none)'}")
        if table.invalid:
            print(f"  ⚠ {len(table.invalid)} quarantined rows — see `arctx trials {table.name}`")


def cli_trials(args) -> int:
    try:
        run_id = resolve_run_id_from_args(args)
        if args.as_json:
            result = run_trials_command(
                run_id=run_id, name=args.name, store_dir=args.store_dir
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        graph = _load_graph(run_id, args.store_dir)
        if args.name is None:
            _print_overview(trial_tables.list_tables(graph))
            return 0
        names = trial_tables.table_names(graph)
        if args.name not in names:
            known = ", ".join(names) if names else "(none yet)"
            raise KeyError(f"unknown table: {args.name!r}. Tables in this run: {known}")
        table = trial_tables.derive_table(graph, args.name)
        if args.best:
            column, maximize = _parse_best(args.best)
            row = trial_tables.best_row(table, column, maximize=maximize)
            if row is None:
                print(
                    f'no active row in "{table.name}" has a numeric "{column}"',
                    file=sys.stderr,
                )
                return 1
            label = "max" if maximize else "min"
            print(
                f"best ({label} {column} = {_format_value(row.metrics.get(column))}): "
                f"{row.step_id}"
                + (f"  {row.title}" if row.title else "")
            )
            for section, key, value in (
                [("col", k, v) for k, v in row.config.items()]
                + [("metric", k, v) for k, v in row.metrics.items()]
            ):
                print(f"  {section} {key} = {_format_value(value)}")
            return 0
        _print_table(table, sort=args.sort, desc=args.desc)
        return 0
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
