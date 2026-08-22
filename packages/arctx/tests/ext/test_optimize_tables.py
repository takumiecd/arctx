"""Tests for derived trial tables (arctx.ext.optimize)."""

from __future__ import annotations

import arctx
from arctx.core.schema.payloads import payload_from_dict
from arctx.core.schema.requirements import Requirement
from arctx.ext.optimize.payloads import TrialPayload
from arctx.ext.optimize.tables import (
    best_row,
    derive_table,
    sort_rows,
    table_names,
    validate_trial,
    validate_trials,
)


def _handle():
    return arctx.init(
        Requirement(requirement_id="req_opt", target_type="task", target_id="opt"),
        run_id="run_opt",
    )


def _trial(tables, config=None, metrics=None, title=None):
    return TrialPayload(
        payload_id="pending",
        target_id="pending",
        tables=tuple(tables),
        config=dict(config or {}),
        metrics=dict(metrics or {}),
        title=title,
    )


def _add(handle, node_id, tables, config=None, metrics=None, title=None):
    return handle.add_step([node_id], _trial(tables, config, metrics, title))


def test_tables_columns_and_rows_derive_from_rows():
    handle = _handle()
    root = handle.root_node_id
    _add(handle, root, ["sweep"], {"tile": 16}, {"latency_ms": 2.41}, title="t16")
    _add(handle, root, ["sweep"], {"tile": 32}, {"latency_ms": 1.87, "occupancy": 0.62})
    _add(handle, root, ["other"], {}, {"score": 1})

    assert table_names(handle.run_graph) == ["sweep", "other"]
    table = derive_table(handle.run_graph, "sweep")
    assert [(c.name, c.section, c.kind) for c in table.columns] == [
        ("tile", "config", "number"),
        ("latency_ms", "metric", "number"),
        ("occupancy", "metric", "number"),
    ]
    assert len(table.rows) == 2
    assert table.rows[0].title == "t16"
    assert not table.invalid


def test_validate_notices_new_table_and_new_column():
    handle = _handle()
    root = handle.root_node_id
    errors, notices = validate_trial(
        handle.run_graph, tables=["sweep"], config={"tile": 16}, metrics={"latency_ms": 2.4}
    )
    assert errors == []
    assert notices == ['new table "sweep" (columns: tile, latency_ms)']

    _add(handle, root, ["sweep"], {"tile": 16}, {"latency_ms": 2.41})
    errors, notices = validate_trial(
        handle.run_graph,
        tables=["sweep"],
        config={"tile": 32},
        metrics={"latency_ms": 1.9, "occupancy": 0.6},
    )
    assert errors == []
    assert notices == ['new column "occupancy" in table "sweep"']


def test_validate_rejects_type_and_section_conflicts():
    handle = _handle()
    root = handle.root_node_id
    step = _add(handle, root, ["sweep"], {"tile": 16}, {"latency_ms": 2.41})

    errors, _ = validate_trial(
        handle.run_graph, tables=["sweep"], config={}, metrics={"latency_ms": "fast"}
    )
    assert len(errors) == 1
    assert '"latency_ms" is number' in errors[0]
    assert step.step_id in errors[0]

    errors, _ = validate_trial(
        handle.run_graph, tables=["sweep"], config={}, metrics={"tile": 32}
    )
    assert len(errors) == 1
    assert '"tile" is a config column' in errors[0]

    errors, _ = validate_trial(
        handle.run_graph, tables=["sweep"], config={"x": [1, 2]}, metrics={"y": 1}
    )
    assert len(errors) == 1
    assert "scalar" in errors[0]


def test_cut_frees_a_mistyped_column():
    handle = _handle()
    root = handle.root_node_id
    # Bypass write validation on purpose: a raw row types latency_ms as str.
    bad = _add(handle, root, ["sweep"], {}, {"latency_ms": "2.41ms"})

    errors, _ = validate_trial(
        handle.run_graph, tables=["sweep"], config={}, metrics={"latency_ms": 1.9}
    )
    assert errors and '"latency_ms" is str' in errors[0]

    handle.cut(bad.step_id, target_kind="step", reason="typo")
    errors, notices = validate_trial(
        handle.run_graph, tables=["sweep"], config={}, metrics={"latency_ms": 1.9}
    )
    assert errors == []
    assert notices == ['new table "sweep" (columns: latency_ms)']

    _add(handle, root, ["sweep"], {}, {"latency_ms": 1.9})
    table = derive_table(handle.run_graph, "sweep")
    # The cut row stays visible but no longer shapes the schema.
    assert [c.kind for c in table.columns] == ["number"]
    assert [row.active for row in table.rows] == [False, True]


def test_conflicting_active_row_is_quarantined_at_read():
    handle = _handle()
    root = handle.root_node_id
    _add(handle, root, ["sweep"], {}, {"latency_ms": 2.41})
    bad = _add(handle, root, ["sweep"], {}, {"latency_ms": "fast"})

    table = derive_table(handle.run_graph, "sweep")
    assert len(table.rows) == 1
    assert len(table.invalid) == 1
    row, reason = table.invalid[0]
    assert row.step_id == bad.step_id
    assert '"latency_ms" is number' in reason


def test_multi_table_membership_and_independent_schemas():
    handle = _handle()
    root = handle.root_node_id
    _add(handle, root, ["sweep", "all"], {"tile": 32}, {"latency_ms": 1.87})
    _add(handle, root, ["all"], {}, {"latency_ms": 3.42})

    assert len(derive_table(handle.run_graph, "sweep").rows) == 1
    all_table = derive_table(handle.run_graph, "all")
    assert len(all_table.rows) == 2
    assert [c.name for c in all_table.columns] == ["tile", "latency_ms"]


def test_best_and_sort():
    handle = _handle()
    root = handle.root_node_id
    _add(handle, root, ["sweep"], {"tile": 16}, {"latency_ms": 2.41})
    fast = _add(handle, root, ["sweep"], {"tile": 32}, {"latency_ms": 1.87})
    cut = _add(handle, root, ["sweep"], {"tile": 64}, {"latency_ms": 0.01})
    handle.cut(cut.step_id, target_kind="step", reason="measurement error")

    table = derive_table(handle.run_graph, "sweep")
    # Cut rows never win --best.
    assert best_row(table, "latency_ms").step_id == fast.step_id
    assert best_row(table, "latency_ms", maximize=True).metrics["latency_ms"] == 2.41
    assert best_row(table, "nope") is None

    ordered = sort_rows(table, "latency_ms")
    assert [row.metrics["latency_ms"] for row in ordered] == [0.01, 1.87, 2.41]
    ordered = sort_rows(table, "tile", descending=True)
    assert [row.config["tile"] for row in ordered] == [64, 32, 16]


def test_trial_payload_roundtrip():
    payload = TrialPayload(
        payload_id="pl_1",
        target_id="t_1",
        tables=("sweep",),
        config={"tile": 32},
        metrics={"latency_ms": 1.87},
        title="trial tile=32",
    )
    decoded = payload_from_dict(payload.to_dict())
    assert isinstance(decoded, TrialPayload)
    assert decoded == payload


def test_many_rows_can_share_one_step():
    handle = _handle()
    step = _add(handle, handle.root_node_id, ["sweep"], {"tile": 16}, {"latency_ms": 2.41})
    handle.attach(step.step_id, _trial(["sweep"], {"tile": 32}, {"latency_ms": 1.87}))
    handle.attach(step.step_id, _trial(["sweep"], {"tile": 64}, {"latency_ms": 2.03}))

    table = derive_table(handle.run_graph, "sweep")
    assert len(handle.run_graph.steps) == 1
    assert [row.config["tile"] for row in table.rows] == [16, 32, 64]
    assert len({row.payload_id for row in table.rows}) == 3
    assert best_row(table, "latency_ms").config["tile"] == 32

    # Cutting the shared Step retires every row it carries.
    handle.cut(step.step_id, target_kind="step")
    table = derive_table(handle.run_graph, "sweep")
    assert [row.active for row in table.rows] == [False, False, False]


def test_validate_trials_checks_a_batch_against_itself():
    handle = _handle()
    errors, notices = validate_trials(
        handle.run_graph,
        [
            (["sweep"], {"tile": 16}, {"latency_ms": 2.41}),
            (["sweep"], {"tile": 32}, {"latency_ms": 1.87, "occupancy": 0.6}),
            (["sweep"], {"tile": 64}, {"latency_ms": 2.03}),
        ],
    )
    assert errors == []
    # One notice per table / column, not per row.
    assert notices == [
        'new table "sweep" (columns: tile, latency_ms)',
        'new column "occupancy" in table "sweep"',
    ]

    errors, _ = validate_trials(
        handle.run_graph,
        [
            (["sweep"], {}, {"latency_ms": 2.41}),
            (["sweep"], {}, {"latency_ms": "fast"}),
        ],
    )
    assert errors == ['row 2: table "sweep": "latency_ms" is number '
                      "(first set by (new)), got 'fast' (str)"]
