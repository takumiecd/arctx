"""Tests for the optimize extension CLI (`arctx trial`, `arctx trials`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from arctx_cli.commands.init import run_init_command
from arctx_cli.ext.optimize import (
    _parse_best,
    _parse_kv,
    run_trial_add_command,
    run_trials_command,
)


def _store_dir(td) -> str:
    return str(Path(td) / "runs")


def _init(td, run_id: str = "run_trials") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(td),
    )


def _add(td, root, **kwargs):
    defaults = dict(
        run_id="run_trials",
        tables=["sweep"],
        config={},
        metrics={},
        input_node_ids=[root] if root else None,
        title=None,
        store_dir=_store_dir(td),
    )
    defaults.update(kwargs)
    return run_trial_add_command(**defaults)


def test_trial_add_creates_step_and_notices_new_table(tmp_path):
    init = _init(tmp_path)
    result = _add(
        tmp_path,
        init["root_node_id"],
        config={"tile": 16},
        metrics={"latency_ms": 2.41},
        title="trial tile=16",
    )
    assert result["step"]["id"].startswith("t_")
    assert result["notices"] == ['new table "sweep" (columns: tile, latency_ms)']

    result = _add(
        tmp_path,
        init["root_node_id"],
        config={"tile": 32},
        metrics={"latency_ms": 1.87, "occupancy": 0.62},
    )
    assert result["notices"] == ['new column "occupancy" in table "sweep"']


def test_trial_add_rejects_type_conflicts_before_writing(tmp_path):
    init = _init(tmp_path)
    _add(tmp_path, init["root_node_id"], metrics={"latency_ms": 2.41})

    with pytest.raises(ValueError, match='"latency_ms" is number'):
        _add(tmp_path, init["root_node_id"], metrics={"latency_ms": "fast"})

    # The rejected trial wrote nothing.
    doc = run_trials_command(
        run_id="run_trials", name="sweep", store_dir=_store_dir(tmp_path)
    )
    assert len(doc["table"]["rows"]) == 1


def test_trial_add_requires_a_metric(tmp_path):
    init = _init(tmp_path)
    with pytest.raises(ValueError, match="at least one --metric"):
        _add(tmp_path, init["root_node_id"], config={"tile": 16})


def test_trials_overview_and_table(tmp_path):
    init = _init(tmp_path)
    _add(
        tmp_path,
        init["root_node_id"],
        tables=["sweep", "all"],
        config={"tile": 32},
        metrics={"latency_ms": 1.87},
    )
    _add(tmp_path, init["root_node_id"], tables=["all"], metrics={"latency_ms": 3.42})

    overview = run_trials_command(
        run_id="run_trials", name=None, store_dir=_store_dir(tmp_path)
    )
    assert [t["name"] for t in overview["tables"]] == ["sweep", "all"]
    assert [len(t["rows"]) for t in overview["tables"]] == [1, 2]

    doc = run_trials_command(
        run_id="run_trials", name="all", store_dir=_store_dir(tmp_path)
    )
    columns = {(c["name"], c["section"], c["kind"]) for c in doc["table"]["columns"]}
    assert ("latency_ms", "metric", "number") in columns

    with pytest.raises(KeyError, match="unknown table"):
        run_trials_command(
            run_id="run_trials", name="nope", store_dir=_store_dir(tmp_path)
        )


def test_trial_rows_survive_reload_as_typed_payloads(tmp_path):
    from arctx.ext.optimize.payloads import TrialPayload

    from arctx_cli.context import resolve_store

    init = _init(tmp_path)
    _add(tmp_path, init["root_node_id"], metrics={"latency_ms": 1.87})

    handle = resolve_store(_store_dir(tmp_path)).load_run("run_trials")
    trials = [
        p for p in handle.run_graph.payloads.values() if isinstance(p, TrialPayload)
    ]
    assert len(trials) == 1
    assert trials[0].tables == ("sweep",)
    assert trials[0].metrics == {"latency_ms": 1.87}


def test_extension_registers_two_cli_commands():
    from arctx.ext import load_extension

    ext = load_extension("optimize")
    names = [command.name for command in ext.cli_commands()]
    assert names == ["trial", "trials"]


def test_value_and_best_parsing():
    parsed = _parse_kv(["tile=32", "name=csr", "ok=true", "ratio=0.5"], "--col")
    assert parsed == {"tile": 32, "name": "csr", "ok": True, "ratio": 0.5}

    with pytest.raises(ValueError, match="KEY=VALUE"):
        _parse_kv(["broken"], "--col")
    with pytest.raises(ValueError, match="scalar"):
        _parse_kv(['x=[1,2]'], "--col")

    assert _parse_best("latency_ms") == ("latency_ms", False)
    assert _parse_best("min:latency_ms") == ("latency_ms", False)
    assert _parse_best("max:occupancy") == ("occupancy", True)
    with pytest.raises(ValueError, match="min:COL or max:COL"):
        _parse_best("avg:latency_ms")


# ---------------------------------------------------------------------------
# Many rows on one Step: a trial is a payload, not a graph record
# ---------------------------------------------------------------------------


def _graph(td):
    from arctx_cli.context import resolve_store

    return resolve_store(_store_dir(td)).load_run("run_trials").run_graph


def test_trial_add_to_appends_rows_without_growing_the_graph(tmp_path):
    init = _init(tmp_path)
    first = _add(
        tmp_path,
        init["root_node_id"],
        config={"tile": 16},
        metrics={"latency_ms": 2.41},
    )
    step_id = first["step"]["step_id"]
    graph = _graph(tmp_path)
    shape = (len(graph.steps), len(graph.nodes))

    second = _add(
        tmp_path,
        None,
        input_node_ids=None,
        to_target=step_id,
        config={"tile": 32},
        metrics={"latency_ms": 1.87},
    )

    assert second["step"]["step_id"] == step_id
    assert second["appended"] is True
    graph = _graph(tmp_path)
    assert (len(graph.steps), len(graph.nodes)) == shape

    table = run_trials_command(
        run_id="run_trials", name="sweep", store_dir=_store_dir(tmp_path)
    )["table"]
    assert len(table["rows"]) == 2
    assert {row["step_id"] for row in table["rows"]} == {step_id}
    # Each row keeps its own identity even though they share a Step.
    assert len({row["payload_id"] for row in table["rows"]}) == 2


def test_trial_add_to_accepts_a_node_or_a_row_id(tmp_path):
    init = _init(tmp_path)
    first = _add(tmp_path, init["root_node_id"], metrics={"latency_ms": 2.41})
    step_id = first["step"]["step_id"]
    output_node = first["step"]["output_node_id"]

    by_node = _add(
        tmp_path, None, to_target=output_node, metrics={"latency_ms": 2.0}
    )
    assert by_node["step"]["step_id"] == step_id

    by_row = _add(
        tmp_path,
        None,
        to_target=by_node["rows"][0]["payload_id"],
        metrics={"latency_ms": 1.5},
    )
    assert by_row["step"]["step_id"] == step_id


def test_trial_add_to_rejects_the_root_and_cut_steps(tmp_path):
    init = _init(tmp_path)
    with pytest.raises(ValueError, match="no producing step"):
        _add(tmp_path, None, to_target=init["root_node_id"], metrics={"x": 1})

    first = _add(tmp_path, init["root_node_id"], metrics={"latency_ms": 2.41})
    step_id = first["step"]["step_id"]

    from arctx_cli.commands.cut import run_cut_command

    run_cut_command(
        run_id="run_trials",
        target_id=step_id,
        target_kind="step",
        reason=None,
        store_dir=_store_dir(tmp_path),
    )
    with pytest.raises(ValueError, match="is cut"):
        _add(tmp_path, None, to_target=step_id, metrics={"latency_ms": 1.0})


def test_trial_add_rows_writes_a_batch_as_one_step(tmp_path):
    init = _init(tmp_path)
    result = _add(
        tmp_path,
        init["root_node_id"],
        title="tile sweep",
        config={"impl": "csr"},
        rows=[
            {"config": {"tile": 16}, "metrics": {"latency_ms": 2.41}},
            {"config": {"tile": 32}, "metrics": {"latency_ms": 1.87}},
            {"config": {"tile": 64}, "metrics": {"latency_ms": 2.03}, "title": "wide"},
        ],
    )

    assert len(result["rows"]) == 3
    assert result["appended"] is False
    graph = _graph(tmp_path)
    assert len(graph.steps) == 1

    table = run_trials_command(
        run_id="run_trials", name="sweep", store_dir=_store_dir(tmp_path)
    )["table"]
    assert [row["config"]["tile"] for row in table["rows"]] == [16, 32, 64]
    # Command-line --col / --title are per-row defaults; a row's own value wins.
    assert {row["config"]["impl"] for row in table["rows"]} == {"csr"}
    assert [row["title"] for row in table["rows"]] == ["tile sweep", "tile sweep", "wide"]


def test_trial_add_rows_rejects_a_self_contradicting_batch(tmp_path):
    init = _init(tmp_path)
    with pytest.raises(ValueError, match=r'row 2: table "sweep": "latency_ms" is number'):
        _add(
            tmp_path,
            init["root_node_id"],
            rows=[
                {"metrics": {"latency_ms": 2.41}},
                {"metrics": {"latency_ms": "fast"}},
            ],
        )
    # Nothing at all was written — not even the first, valid row.
    graph = _graph(tmp_path)
    assert len(graph.steps) == 0


def test_trial_add_rows_reports_bad_row_input(tmp_path):
    init = _init(tmp_path)
    with pytest.raises(ValueError, match="unknown key"):
        _add(
            tmp_path,
            init["root_node_id"],
            rows=[{"metric": {"latency_ms": 1.0}}],
        )
    with pytest.raises(ValueError, match="row 2: a trial needs at least one"):
        _add(
            tmp_path,
            init["root_node_id"],
            rows=[{"metrics": {"latency_ms": 1.0}}, {"config": {"tile": 8}}],
        )


def test_read_row_objects_accepts_jsonl_and_arrays(tmp_path):
    from arctx_cli.ext.optimize import _read_row_objects

    jsonl = tmp_path / "rows.jsonl"
    jsonl.write_text(
        '# a comment\n{"metrics": {"latency_ms": 1.0}}\n\n{"metrics": {"latency_ms": 2.0}}\n',
        encoding="utf-8",
    )
    assert _read_row_objects(str(jsonl)) == [
        {"metrics": {"latency_ms": 1.0}},
        {"metrics": {"latency_ms": 2.0}},
    ]

    array = tmp_path / "rows.json"
    array.write_text('[{"metrics": {"latency_ms": 1.0}}]', encoding="utf-8")
    assert _read_row_objects(str(array)) == [{"metrics": {"latency_ms": 1.0}}]

    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no rows"):
        _read_row_objects(str(empty))
