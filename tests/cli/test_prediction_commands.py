"""Detailed tests for predicted-side CLI commands."""

from __future__ import annotations

from optagent.cli.commands.extend import run_extend_command
from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.predict import run_predict_command
from optagent.cli.commands.promote import run_promote_command, run_promote_plan_command
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


def test_extend_creates_predicted_plan_with_inputs(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)

    plans = run_extend_command(
        run_id=run_id,
        node_id="n_0001",
        planner="future-planner",
        max_plans=1,
        store_dir=store_dir,
        action_type="analysis",
        intent="extend future",
        inputs={"branch": "a"},
    )["plans"]

    assert plans[0]["grounded_node_id"] == "n_0001"
    assert plans[0]["intent"] == "extend future"
    assert plans[0]["inputs"] == {"branch": "a"}
    assert plans[0]["metadata"]["planner"] == "future-planner"


def test_predict_adds_multiple_transitions_and_result_payloads(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    plan_id = run_extend_command(
        run_id=run_id,
        node_id="n_0001",
        planner="future-planner",
        max_plans=1,
        store_dir=store_dir,
    )["plans"][0]["plan_id"]

    transitions = run_predict_command(
        run_id=run_id,
        plan_id=plan_id,
        predictor="predictor-x",
        max_outcomes=3,
        store_dir=store_dir,
    )["predictions"]

    assert len(transitions) == 3
    assert [t["parent_plan_id"] for t in transitions] == [plan_id, plan_id, plan_id]
    assert [t["metadata"]["ordinal"] for t in transitions] == [0, 1, 2]

    handle = JsonlRunStore(store_dir).load_run(run_id)
    payloads = [
        handle.predicted_dag.payloads_for(t["transition_id"], payload_type="result")[0]
        for t in transitions
    ]
    assert [p.metadata["predictor"] for p in payloads] == [
        "predictor-x",
        "predictor-x",
        "predictor-x",
    ]


def test_promote_plan_preserves_source_metadata(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    predicted_plan = run_extend_command(
        run_id=run_id,
        node_id="n_0001",
        planner="future-planner",
        max_plans=1,
        store_dir=store_dir,
        intent="future action",
    )["plans"][0]

    promoted = run_promote_plan_command(
        run_id=run_id,
        predicted_plan_id=predicted_plan["plan_id"],
        to_observed_node_id="n_0000",
        store_dir=store_dir,
        user_id="alice",
    )["plans"][0]

    assert promoted["grounded_node_id"] == "n_0000"
    assert promoted["intent"] == "future action"
    assert promoted["metadata"]["source_predicted_plan_id"] == predicted_plan["plan_id"]
    assert promoted["metadata"]["user_id"] == "alice"
    assert promoted["metadata"]["promotion_id"] == "promotion_0001"


def test_promote_transition_attaches_match_payload(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    predicted_plan_id = run_extend_command(
        run_id=run_id,
        node_id="n_0001",
        planner="future-planner",
        max_plans=1,
        store_dir=store_dir,
    )["plans"][0]["plan_id"]
    predicted_transition_id = run_predict_command(
        run_id=run_id,
        plan_id=predicted_plan_id,
        predictor="predictor",
        max_outcomes=1,
        store_dir=store_dir,
    )["predictions"][0]["transition_id"]
    observed_plan_id = run_plan_command(
        run_id=run_id,
        planner="planner",
        max_plans=1,
        store_dir=store_dir,
        from_node_id="n_0000",
    )["plans"][0]["plan_id"]

    transition = run_promote_command(
        run_id=run_id,
        predicted_transition_id=predicted_transition_id,
        status="completed",
        plan_id=observed_plan_id,
        metrics={"score": 2.0},
        store_dir=store_dir,
        user_id="alice",
    )["transition"]

    handle = JsonlRunStore(store_dir).load_run(run_id)
    result_payload = handle.observed_dag.payloads_for(
        transition["transition_id"], payload_type="result"
    )[0]
    match_payload = handle.observed_dag.payloads_for(
        transition["transition_id"], payload_type="match"
    )[0]

    assert transition["metadata"]["user_id"] == "alice"
    assert result_payload.metrics == {"score": 2.0}
    assert match_payload.matched_transition_id == predicted_transition_id
    assert match_payload.match_status == "compatible"
