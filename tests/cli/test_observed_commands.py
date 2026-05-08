"""Detailed tests for observed-side CLI commands."""

from __future__ import annotations

import pytest

from optagent.cli.commands.derive import run_derive_command
from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.observe import _parse_metrics, run_observe_command
from optagent.cli.commands.plan import _parse_inputs, run_plan_command
from optagent.cli.commands.show import run_show_command
from optagent.cli.commands.trace import run_trace_command
from optagent.storage.jsonl import JsonlRunStore


def _init(store_dir: str) -> str:
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_a",
        store_dir=store_dir,
    )
    return "run_a"


def test_parse_input_and_metric_validation():
    assert _parse_inputs(["a=b", "c=d=e"]) == {"a": "b", "c": "d=e"}
    assert _parse_metrics(["score=1.25"]) == {"score": 1.25}

    with pytest.raises(ValueError):
        _parse_inputs(["missing_equals"])
    with pytest.raises(ValueError):
        _parse_metrics(["score"])
    with pytest.raises(ValueError):
        _parse_metrics(["score=nan-ish"])


def test_plan_records_inputs_and_user_metadata(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)

    plans = run_plan_command(
        run_id=run_id,
        planner="planner-x",
        max_plans=2,
        store_dir=store_dir,
        from_node_id="n_0000",
        action_type="benchmark",
        intent="run baseline",
        inputs={"shape": "small"},
        user_id="alice",
    )["plans"]

    assert [p["plan_id"] for p in plans] == ["plan_0001", "plan_0002"]
    assert plans[0]["grounded_node_id"] == "n_0000"
    assert plans[0]["action_type"] == "benchmark"
    assert plans[0]["inputs"] == {"shape": "small"}
    assert plans[0]["metadata"]["planner"] == "planner-x"
    assert plans[0]["metadata"]["user_id"] == "alice"


def test_observe_attaches_result_and_show_can_fetch_payload(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    plan_id = run_plan_command(
        run_id=run_id,
        planner="planner",
        max_plans=1,
        store_dir=store_dir,
        from_node_id="n_0000",
    )["plans"][0]["plan_id"]

    transition = run_observe_command(
        run_id=run_id,
        plan_id=plan_id,
        status="completed",
        artifacts=["artifact.bin"],
        raw_outputs=["raw.txt"],
        logs=["stderr.log"],
        metrics={"latency_ms": 1.5},
        errors=["warning"],
        store_dir=store_dir,
        user_id="alice",
    )["transition"]

    store = JsonlRunStore(store_dir)
    handle = store.load_run(run_id)
    result_payload = handle.observed_dag.payloads_for(
        transition["transition_id"], payload_type="result"
    )[0]

    payload_view = run_show_command(
        run_id=run_id,
        node_id=None,
        plan_id=None,
        transition_id=None,
        payload_id=result_payload.payload_id,
        store_dir=store_dir,
    )["payload"]

    assert transition["metadata"]["user_id"] == "alice"
    assert payload_view["payload_type"] == "result"
    assert payload_view["metrics"] == {"latency_ms": 1.5}
    assert payload_view["artifacts"] == ["artifact.bin"]
    assert payload_view["raw_outputs"] == ["raw.txt"]
    assert payload_view["logs"] == ["stderr.log"]
    assert payload_view["errors"] == ["warning"]


def test_derive_and_trace_include_payload_refs(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    plan_id = run_plan_command(
        run_id=run_id,
        planner="planner",
        max_plans=1,
        store_dir=store_dir,
        from_node_id="n_0000",
    )["plans"][0]["plan_id"]
    transition = run_observe_command(
        run_id=run_id,
        plan_id=plan_id,
        status="completed",
        artifacts=["artifact.bin"],
        raw_outputs=["raw.txt"],
        logs=["stderr.log"],
        metrics=None,
        errors=None,
        store_dir=store_dir,
    )["transition"]

    derived = run_derive_command(
        run_id=run_id,
        transition_id=transition["transition_id"],
        derived_type="finding",
        payload={"text": "learned"},
        payload_id="custom_payload",
        generator="test",
        confidence=0.75,
        store_dir=store_dir,
        user_id="alice",
    )["record"]

    trace = run_trace_command(
        run_id=run_id,
        from_node_id=transition["to_node_id"],
        depth=1,
        store_dir=store_dir,
    )["history"]

    assert derived["payload_id"] == "custom_payload"
    assert derived["metadata"]["user_id"] == "alice"
    assert trace["transition_ids"] == [transition["transition_id"]]
    assert trace["derived_payload_ids"] == ["custom_payload"]
    assert trace["artifact_refs"] == ["artifact.bin", "raw.txt", "stderr.log"]


def test_observe_rejects_second_transition_for_same_plan(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    plan_id = run_plan_command(
        run_id=run_id,
        planner="planner",
        max_plans=1,
        store_dir=store_dir,
        from_node_id="n_0000",
    )["plans"][0]["plan_id"]

    kwargs = dict(
        run_id=run_id,
        plan_id=plan_id,
        status="completed",
        artifacts=None,
        raw_outputs=None,
        logs=None,
        metrics=None,
        errors=None,
        store_dir=store_dir,
    )
    run_observe_command(**kwargs)
    with pytest.raises(ValueError):
        run_observe_command(**kwargs)
