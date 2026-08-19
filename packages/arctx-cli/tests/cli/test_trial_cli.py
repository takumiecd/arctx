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
        input_node_ids=[root],
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
