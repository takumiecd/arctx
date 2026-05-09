"""Detailed tests for observed-side CLI commands."""

from __future__ import annotations

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.observe import _parse_metrics, run_observe_command
from optagent.cli.commands.plan import _parse_kv, run_plan_command
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


def test_parse_kv_and_metric_validation():
    assert _parse_kv(["a=b", "c=d=e"]) == {"a": "b", "c": "d=e"}
    assert _parse_metrics(["score=1.25"]) == {"score": 1.25}

    with pytest.raises(ValueError):
        _parse_kv(["missing_equals"])
    with pytest.raises(ValueError):
        _parse_metrics(["score"])
    with pytest.raises(ValueError):
        _parse_metrics(["score=nan-ish"])


def test_plan_records_intent_and_action_type(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)

    it = run_plan_command(
        run_id=run_id,
        input_node_ids=["n_0000"],
        action_type="analysis",
        intent="run baseline",
        inputs={"shape": "small"},
        store_dir=store_dir,
        user_id="alice",
    )["input_transition"]

    assert it["input_node_ids"] == ["n_0000"]
    # Check the PlanPayload was stored
    store = JsonlRunStore(store_dir)
    handle = store.load_run(run_id)
    it_id = it["input_transition_id"]
    plan_payloads = handle.run_graph.payloads_for_input_transition(it_id, payload_type="plan_payload")
    assert len(plan_payloads) == 1
    assert plan_payloads[0].intent == "run baseline"
    assert plan_payloads[0].action_type == "analysis"
    assert plan_payloads[0].inputs == {"shape": "small"}


def test_observe_attaches_result_and_show_can_fetch_payload(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    it_id = run_plan_command(
        run_id=run_id,
        input_node_ids=["n_0000"],
        action_type="analysis",
        intent="x",
        store_dir=store_dir,
    )["input_transition"]["input_transition_id"]

    ot = run_observe_command(
        run_id=run_id,
        input_transition_id=it_id,
        status="completed",
        artifacts=["artifact.bin"],
        raw_outputs=["raw.txt"],
        logs=["stderr.log"],
        metrics={"latency_ms": 1.5},
        errors=["warning"],
        store_dir=store_dir,
        user_id="alice",
    )["output_transition"]

    store = JsonlRunStore(store_dir)
    handle = store.load_run(run_id)
    ot_id = ot["output_transition_id"]
    result_payloads = handle.run_graph.payloads_for_output_transition(ot_id, payload_type="result")
    assert len(result_payloads) == 1
    rp = result_payloads[0]

    payload_view = run_show_command(
        run_id=run_id,
        node_id=None,
        input_transition_id=None,
        output_transition_id=None,
        payload_id=rp.payload_id,
        with_payloads=False, outputs=False,
        store_dir=store_dir,
    )["payload"]

    assert payload_view["payload_type"] == "result"
    assert payload_view["metrics"] == {"latency_ms": 1.5}
    assert payload_view["artifacts"] == ["artifact.bin"]


def test_trace_includes_artifact_refs(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    it_id = run_plan_command(
        run_id=run_id, input_node_ids=["n_0000"], action_type="analysis",
        intent="x", store_dir=store_dir,
    )["input_transition"]["input_transition_id"]
    ot = run_observe_command(
        run_id=run_id,
        input_transition_id=it_id,
        status="completed",
        artifacts=["artifact.bin"],
        raw_outputs=["raw.txt"],
        logs=["stderr.log"],
        metrics=None,
        errors=None,
        store_dir=store_dir,
    )["output_transition"]

    trace = run_trace_command(
        run_id=run_id,
        from_node_id=ot["to_node_id"],
        depth=1,
        store_dir=store_dir,
    )["history"]

    assert ot["output_transition_id"] in trace["output_transition_ids"]
    assert "artifact.bin" in trace["artifact_refs"]
    assert "raw.txt" in trace["artifact_refs"]
    assert "stderr.log" in trace["artifact_refs"]
