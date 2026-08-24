"""CLI for the optimize extension: ``arctx trial`` and ``arctx trials``.

``trial add`` mirrors ``arctx add`` (one Step from input nodes, defaulting to
the current lane's single active frontier) but writes a typed TrialPayload and
validates it against the derived schema of every listed table before anything
is written: new columns grow a table with a notice, type conflicts are errors.

A trial is a *payload*, not a graph record: a Step can carry as many rows as
you like. A sweep is therefore one Step with N rows, not N Steps — either
written in one shot (``--rows FILE``) or appended one at a time to an existing
Step (``--to STEP_ID``). Only a bare ``trial add`` grows the graph.

``trials`` is read-only: with no argument it lists every table with its
columns; with a table name it prints the derived comparison table.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import arctx.ext.optimize.payloads  # noqa: F401  (registers the trial decoder)
from arctx.core.cuts import inactive_step_ids
from arctx.ext.optimize import tables as trial_tables
from arctx.ext.optimize.payloads import TrialPayload

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.commands._targets import resolve_target_kind, step_view
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
    if isinstance(value, float) and not math.isfinite(value):
        # json.loads accepts NaN / Infinity / -Infinity, and 1e309 overflows to
        # inf. None of them are sortable or writable as JSON.
        raise ValueError(
            f"value must be a finite number, got {text!r}"
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
# Rows
# ---------------------------------------------------------------------------

ROW_KEYS = ("tables", "title", "config", "metrics")


@dataclass(frozen=True)
class TrialRowSpec:
    """One prospective trial row, before it is written."""

    tables: tuple[str, ...]
    config: dict
    metrics: dict
    title: str | None


def _read_row_objects(source: str) -> list[dict]:
    """Read batch rows from a JSONL / JSON-array file (``-`` = stdin)."""
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        raise ValueError(f"no rows in {source!r}")
    if stripped.startswith("["):
        data = json.loads(stripped)
        if not isinstance(data, list):
            raise ValueError(f"{source}: expected a JSON array of rows")
        return data
    rows: list[dict] = []
    for lineno, line in enumerate(stripped.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}:{lineno}: {exc}") from exc
    if not rows:
        raise ValueError(f"no rows in {source!r}")
    return rows


def _scalar_map(value, label: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    out: dict = {}
    for key, val in value.items():
        if val is None or isinstance(val, (dict, list)):
            raise ValueError(
                f'{label}: value for "{key}" must be a scalar (number / bool / string)'
            )
        out[str(key)] = val
    return out


def _row_specs(
    row_objects: list[dict] | None,
    *,
    tables: list[str],
    config: dict,
    metrics: dict,
    title: str | None,
) -> list[TrialRowSpec]:
    """Normalize CLI input into the rows that will be written.

    Without ``--rows`` this is the single row spelled with ``--col`` /
    ``--metric``. With ``--rows`` each object contributes one row, and the
    command-line ``--table`` / ``--col`` / ``--metric`` / ``--title`` act as
    defaults every row inherits (a row's own values win).
    """
    if row_objects is None:
        return [TrialRowSpec(tuple(tables), dict(config), dict(metrics), title)]

    specs: list[TrialRowSpec] = []
    for index, obj in enumerate(row_objects, 1):
        if not isinstance(obj, dict):
            raise ValueError(
                f"row {index}: each row must be a JSON object, got {type(obj).__name__}"
            )
        unknown = sorted(set(obj) - set(ROW_KEYS))
        if unknown:
            raise ValueError(
                f"row {index}: unknown key(s) {', '.join(unknown)} "
                f"(expected: {', '.join(ROW_KEYS)})"
            )
        row_tables = obj.get("tables") or tables
        if isinstance(row_tables, str):
            row_tables = [row_tables]
        names = [str(name).strip() for name in row_tables]
        if not names or any(not name for name in names):
            raise ValueError(f"row {index}: table names cannot be empty")
        row_title = obj.get("title", title)
        specs.append(
            TrialRowSpec(
                tables=tuple(names),
                config={**config, **_scalar_map(obj.get("config"), f"row {index}: config")},
                metrics={
                    **metrics,
                    **_scalar_map(obj.get("metrics"), f"row {index}: metrics"),
                },
                title=None if row_title is None else str(row_title),
            )
        )
    return specs


def _resolve_target_step(handle, target_id: str) -> str:
    """Resolve ``--to`` (a step, a node, or a trial row id) to a Step id."""
    graph = handle.run_graph
    kind = resolve_target_kind(handle, target_id)
    if kind == "node":
        step_id = graph.step_to_node(target_id)
        if step_id is None:
            raise ValueError(
                f"{target_id} has no producing step (it is the run root). "
                f"Pass a step id, or drop --to to start a new trial step."
            )
    elif kind == "payload":
        payload = graph.payloads[target_id]
        if payload.target_kind != "step":
            raise ValueError(
                f"{target_id} is attached to a node; pass the node id itself "
                f"or a step id to --to"
            )
        step_id = payload.target_id
    else:
        step_id = target_id
    if step_id in inactive_step_ids(graph):
        raise ValueError(
            f"step {step_id} is cut — rows appended to it would be inactive. "
            f"Uncut it (`arctx uncut {step_id}`) or drop --to."
        )
    return step_id


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
    add.add_argument(
        "--to",
        default=None,
        dest="to_target",
        metavar="TARGET_ID",
        help=(
            "Append the row(s) to an existing trial Step instead of creating "
            "one. Takes a step id, the node it produced, or another row's "
            "payload id. The graph does not grow."
        ),
    )
    add.add_argument(
        "--rows",
        default=None,
        metavar="PATH",
        help=(
            "Read many rows from a JSONL file or a JSON array ('-' for stdin); "
            "keys: tables / title / config / metrics. All rows land on one "
            "Step, and --table/--col/--metric/--title act as per-row defaults."
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


def _trial_payload(spec: TrialRowSpec) -> TrialPayload:
    return TrialPayload(
        payload_id="pending",
        target_id="pending",
        tables=spec.tables,
        config=spec.config,
        metrics=spec.metrics,
        title=spec.title,
    )


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
    to_target: str | None = None,
    rows: list[dict] | None = None,
) -> dict:
    table_names = [name.strip() for name in tables]
    if any(not name for name in table_names):
        raise ValueError("--table NAME cannot be empty")
    specs = _row_specs(
        rows, tables=table_names, config=config, metrics=metrics, title=title
    )
    for index, spec in enumerate(specs, 1):
        if not spec.metrics:
            where = f"row {index}: " if len(specs) > 1 else ""
            raise ValueError(
                f"{where}a trial needs at least one --metric KEY=VALUE (record "
                f"results, not intentions — use `arctx add` for unscored steps)"
            )

    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    ensure_lane_open(handle, lane_id, force=force)

    target_step_id: str | None = None
    if to_target is not None:
        target_step_id = _resolve_target_step(handle, to_target)
    elif not input_node_ids:
        input_node_ids = _default_input_node_ids(handle, lane_id or "default")

    errors, notices = trial_tables.validate_trials(
        handle.run_graph,
        [(spec.tables, spec.config, spec.metrics) for spec in specs],
    )
    if errors:
        raise ValueError("\n".join(errors))

    before = graph_counts(handle)
    pending = list(specs)
    written: list[TrialPayload] = []
    if target_step_id is None:
        seen = set(handle.run_graph.payloads)
        step = handle.add_step(
            input_node_ids,
            _trial_payload(pending.pop(0)),
            user_id=user_id,
            lane_id=lane_id,
        )
        target_step_id = step.step_id
        written = [
            payload
            for payload_id, payload in handle.run_graph.payloads.items()
            if payload_id not in seen and isinstance(payload, TrialPayload)
        ]
    for spec in pending:
        written.append(
            handle.attach(
                target_step_id,
                _trial_payload(spec),
                user_id=user_id,
                lane_id=lane_id,
            )
        )

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane_id,
        before=before,
        require_lane_open=not force,
    )
    return {
        "step": step_view(handle.run_graph.steps[target_step_id]),
        "rows": [
            {
                "payload_id": payload.payload_id,
                "title": payload.title,
                "tables": list(payload.tables),
            }
            for payload in written
        ],
        "appended": to_target is not None,
        "notices": notices,
    }


def cli_trial(args) -> int:
    try:
        if args.trial_command != "add":
            raise ValueError(f"unknown trial command: {args.trial_command!r}")
        if args.to_target and args.input_nodes:
            raise ValueError(
                "--to and --from are exclusive: --to appends rows to an "
                "existing step, --from starts a new one"
            )
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
            to_target=args.to_target,
            rows=None if args.rows is None else _read_row_objects(args.rows),
        )
        for notice in result["notices"]:
            # stdout stays pure JSON so `trial add | jq -r .step_id` works.
            print(f"notice: {notice}", file=sys.stderr)
        view = dict(result["step"])
        view["rows"] = [row["payload_id"] for row in result["rows"]]
        view["appended"] = result["appended"]
        print(json.dumps(view, ensure_ascii=False, indent=2))
        strict_rc = warn_if_invalid(run_id, args.store_dir, command_name="trial add")
        return strict_rc or 0
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
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


def _shares_steps(table: trial_tables.TrialTable) -> bool:
    """Report whether some Step in this table carries more than one row."""
    seen: set[str] = set()
    for row in table.rows:
        if row.step_id in seen:
            return True
        seen.add(row.step_id)
    return False


def _print_table(table: trial_tables.TrialTable, *, sort: str | None, desc: bool) -> None:
    rows = trial_tables.sort_rows(table, sort, descending=desc) if sort else table.rows
    has_title = any(row.title for row in rows)
    # A row's own id is its payload id; the step is shown only when it groups
    # several rows, which is what makes a sweep one graph record instead of N.
    show_step = _shares_steps(table)
    header = ["row"]
    if show_step:
        header.append("step")
    if has_title:
        header.append("title")
    header += ["lane"]
    header += [col.name for col in table.columns]
    header += ["status"]
    lines = [header]
    for row in rows:
        line = [row.payload_id[:10]]
        if show_step:
            line.append(row.step_id[:10])
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
            print(f"⚠ {row.payload_id[:10]} quarantined: {reason}")


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
            # `--best` is the one read path that never consulted `invalid`, so a
            # row quarantined over an *unrelated* column simply vanished from
            # the comparison and the winner was silently wrong. Quarantine is a
            # schema conflict, not a statement about this metric: say what was
            # left out, on stderr so stdout stays machine-clean.
            hidden = [
                (hidden_row, reason)
                for hidden_row, reason in table.invalid
                if trial_tables.value_kind(hidden_row.metrics.get(column)) == "number"
            ]
            for hidden_row, reason in hidden:
                print(
                    f"notice: {hidden_row.payload_id} has {column} = "
                    f"{_format_value(hidden_row.metrics.get(column))} but is "
                    f"excluded from this comparison — {reason}",
                    file=sys.stderr,
                )
            if hidden:
                print(
                    f"notice: {len(hidden)} row(s) with a numeric \"{column}\" were "
                    f"quarantined; see `arctx trials {table.name}`",
                    file=sys.stderr,
                )
            if row is None:
                if hidden:
                    # "no active row has a numeric column" would be false here:
                    # the rows are active, just hidden by a schema conflict.
                    print(
                        f'every row in "{table.name}" with a numeric "{column}" is '
                        f"quarantined; fix the conflict above, or cut the row that "
                        f"fixed the column type",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    f'no active row in "{table.name}" has a numeric "{column}"',
                    file=sys.stderr,
                )
                return 1
            label = "max" if maximize else "min"
            print(
                f"best ({label} {column} = {_format_value(row.metrics.get(column))}): "
                f"{row.payload_id}"
                + (f"  {row.title}" if row.title else "")
            )
            print(f"  step {row.step_id}")
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
