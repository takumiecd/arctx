import json

import optagent
from optagent import ActionResult, DerivedRecord, Requirement
from optagent.storage import JsonlRunStore


def _requirement() -> Requirement:
    return Requirement(
        requirement_id="req_kernel",
        target_type="kernel",
        target_id="csc_linear",
    )


def _run_with_history():
    run = optagent.init(_requirement(), run_id="run_test")
    plan = run.plan(from_state_id="s_obs_0000")[0]
    predicted = run.predict(plan.plan_id, max_outcomes=2)
    result = ActionResult(
        result_id="r_0001",
        execution_plan_id=plan.plan_id,
        status="completed",
        raw_outputs=("raw/profile.txt",),
        metrics={"latency_ms": 1.5},
    )
    derived = DerivedRecord(
        derived_id="d_0001",
        source_transition_id="t_obs_0001",
        derived_type="evidence",
        payload={"latency_ms": 1.5},
        generator="test",
    )
    run.promote(
        mode="transition",
        predicted_transition_id=predicted[1].transition_id,
        execution_plan_id=plan.plan_id,
        action_result=result,
        derived_records=[derived],
    )
    return run


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_jsonl_store_saves_run_directory(tmp_path):
    run = _run_with_history()
    store = JsonlRunStore(tmp_path)

    run_path = store.save_run(run)

    assert run_path == tmp_path / "run_test"
    assert (run_path / "run.json").exists()
    assert (run_path / "states.jsonl").exists()
    assert (run_path / "execution_plans.jsonl").exists()
    assert (run_path / "prediction_plans.jsonl").exists()
    assert (run_path / "predicted_transitions.jsonl").exists()
    assert (run_path / "observed_transitions.jsonl").exists()
    assert (run_path / "derived_records.jsonl").exists()


def test_jsonl_store_writes_human_readable_records(tmp_path):
    run = _run_with_history()
    store = JsonlRunStore(tmp_path)

    run_path = store.save_run(run)

    manifest = json.loads((run_path / "run.json").read_text())
    assert manifest["run_id"] == "run_test"
    assert "current_observed_state_id" not in manifest
    assert manifest["requirement"]["requirement_id"] == "req_kernel"

    states = _read_jsonl(run_path / "states.jsonl")
    assert {row["state_id"] for row in states} >= {"s_obs_0000", "s_pred_0000"}
    assert {row["dag"] for row in states} == {"trace", "prediction"}

    observed = _read_jsonl(run_path / "observed_transitions.jsonl")
    assert observed[0]["transition_id"] == "t_obs_0001"
    assert observed[0]["action_result"]["raw_outputs"] == ["raw/profile.txt"]
    assert observed[0]["matched_predicted_transition_id"] == "t_pred_0002"

    derived = _read_jsonl(run_path / "derived_records.jsonl")
    assert derived[0]["derived_id"] == "d_0001"
    assert derived[0]["payload"]["latency_ms"] == 1.5


def test_jsonl_store_loads_run_and_can_continue_ids(tmp_path):
    run = _run_with_history()
    store = JsonlRunStore(tmp_path)
    store.save_run(run)

    loaded = store.load_run("run_test")

    assert loaded.run_id == run.run_id
    transition = loaded.trace_dag.transitions["t_obs_0001"]
    assert loaded.trace(state_id=transition.to_observed_state_id).observed_transition_ids == (
        "t_obs_0001",
    )
    assert loaded.trace(state_id=transition.to_observed_state_id).derived_record_ids == (
        "d_0001",
    )
    assert loaded.prediction_dag.predicted_transition_ids_for_plan("p_exec_0001") == [
        "t_pred_0001",
        "t_pred_0002",
    ]

    next_plan = loaded.plan(from_state_id=transition.to_observed_state_id)[0]
    assert next_plan.plan_id == "p_exec_0002"


def test_run_handle_can_save_with_store(tmp_path):
    run = _run_with_history()
    store = JsonlRunStore(tmp_path)

    run_path = run.save(store)

    assert run_path == tmp_path / "run_test"


def test_jsonl_store_list_runs_returns_summaries(tmp_path):
    req_a = Requirement(requirement_id="req_a", target_type="code", target_id="mod_a")
    req_b = Requirement(requirement_id="req_b", target_type="kernel", target_id="mod_b")
    store = JsonlRunStore(tmp_path)

    run_a = optagent.init(req_a, run_id="run_a")
    run_b = optagent.init(req_b, run_id="run_b")
    store.save_run(run_a)
    store.save_run(run_b)

    summaries = store.list_runs()
    assert len(summaries) == 2
    ids = {s["run_id"] for s in summaries}
    assert ids == {"run_a", "run_b"}

    by_id = {s["run_id"]: s for s in summaries}
    assert by_id["run_a"]["requirement_id"] == "req_a"
    assert by_id["run_a"]["target_type"] == "code"
    assert "current_observed_state_id" not in by_id["run_a"]


def test_jsonl_store_list_runs_empty(tmp_path):
    store = JsonlRunStore(tmp_path)
    assert store.list_runs() == []


def test_jsonl_store_list_runs_ignores_invalid_directories(tmp_path):
    store = JsonlRunStore(tmp_path)
    (tmp_path / "not_a_run").mkdir()
    (tmp_path / "not_a_run" / "foo.txt").write_text("bar")

    assert store.list_runs() == []
