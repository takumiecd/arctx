import optagent
import pytest
from optagent.core import (
    ActionResult,
    DerivedRecord,
    ExecutionPlan,
    PredictionPath,
    PredictionStepRef,
    Requirement,
)


def _requirement() -> Requirement:
    return Requirement(
        requirement_id="req_kernel",
        target_type="kernel",
        target_id="csc_linear",
    )


def test_init_creates_trace_and_prediction_roots():
    run = optagent.init(_requirement(), run_id="run_test")

    assert run.run_id == "run_test"
    assert run.root_observed_state_id == "s_obs_0000"
    assert run.trace_dag.depth(0)[0].state_kind == "observed"
    assert run.prediction_dag.root_predicted_state_id == "s_pred_0000"

    prediction_root = run.prediction_dag.nodes[run.prediction_dag.root_predicted_state_id]
    assert prediction_root.state_kind == "predicted"
    assert prediction_root.anchor_observed_state_id == "s_obs_0000"
    assert prediction_root.snapshot_hash == run.trace_dag.nodes["s_obs_0000"].snapshot_hash


def test_plan_predict_promote_transition_refresh_loop():
    run = optagent.init(_requirement(), run_id="run_test")

    plans = run.plan(from_state_id="s_obs_0000")
    assert len(plans) == 1
    assert isinstance(plans[0], ExecutionPlan)
    assert plans[0].plan_kind == "execution"

    predicted = run.predict(plans[0].plan_id, max_outcomes=2)
    assert [transition.parent_plan_id for transition in predicted] == [
        plans[0].plan_id,
        plans[0].plan_id,
    ]
    selection = run.select_prediction(predicted_transition_id=predicted[1].transition_id)
    assert selection.selected_transition_ids == (predicted[1].transition_id,)

    result = ActionResult(
        result_id="r_0001",
        execution_plan_id=plans[0].plan_id,
        status="completed",
        raw_outputs=("raw/profile.txt",),
        metrics={"latency_ms": 1.5},
    )
    derived = DerivedRecord(
        derived_id="d_0001",
        source_transition_id="t_obs_0001",
        derived_type="observation",
        payload={"summary": "profile completed"},
        generator="test",
    )
    observed = run.promote(
        mode="transition",
        predicted_transition_id=predicted[1].transition_id,
        action_result=result,
        execution_plan_id=plans[0].plan_id,
        derived_records=[derived],
    )

    assert observed.matched_predicted_transition_id == predicted[1].transition_id
    context = run.trace(
        state_id=observed.to_observed_state_id,
        include_derived=True,
        include_raw_refs=True,
    )
    assert context.observed_transition_ids == (observed.transition_id,)
    assert context.action_result_ids == ("r_0001",)
    assert context.derived_record_ids == ("d_0001",)
    assert context.artifact_refs == ("raw/profile.txt",)

    refreshed = run.refresh(from_state_id=observed.to_observed_state_id)
    root = refreshed.nodes[refreshed.root_predicted_state_id]
    assert refreshed.anchor_observed_state_id == observed.to_observed_state_id
    assert root.snapshot_hash == run.trace_dag.nodes[observed.to_observed_state_id].snapshot_hash


def test_prediction_plan_path_promotes_to_execution_plan():
    run = optagent.init(_requirement(), run_id="run_test")
    root_id = run.prediction_dag.root_predicted_state_id

    prediction_plan = run.extend(state_id=root_id)[0]
    predicted = run.predict(prediction_plan.plan_id)[0]
    path = PredictionPath(
        path_id="path_pred_0001",
        anchor_observed_state_id="s_obs_0000",
        steps=(
            PredictionStepRef(
                prediction_plan_id=prediction_plan.plan_id,
                selected_predicted_transition_id=predicted.transition_id,
                from_predicted_state_id=predicted.from_state_id,
                to_predicted_state_id=predicted.to_predicted_state_id,
            ),
        ),
    )

    promoted = run.promote(
        mode="plan",
        prediction_path=path,
        to_observed_state_id="s_obs_0000",
    )

    assert len(promoted) == 1
    assert promoted[0].plan_kind == "execution"
    assert promoted[0].from_observed_state_id == "s_obs_0000"
    assert promoted[0].metadata["source_prediction_plan_id"] == prediction_plan.plan_id
    assert promoted[0].metadata["selected_predicted_transition_id"] == predicted.transition_id


def test_observe_records_result_without_prediction_match():
    run = optagent.init(_requirement(), run_id="run_test")
    plan = run.plan(from_state_id="s_obs_0000")[0]
    assert isinstance(plan, ExecutionPlan)
    result = ActionResult(
        result_id="r_0001",
        execution_plan_id=plan.plan_id,
        status="completed",
    )

    observed = run.observe(plan.plan_id, result)

    assert observed.matched_predicted_transition_id is None
    assert observed.prediction_match is None
    assert run.history(state_id=observed.to_observed_state_id).execution_plan_ids == (
        plan.plan_id,
    )


def test_promote_transition_requires_execution_plan():
    run = optagent.init(_requirement(), run_id="run_test")
    prediction_plan = run.extend(state_id=run.prediction_dag.root_predicted_state_id)[0]
    predicted = run.predict(prediction_plan.plan_id)[0]
    result = ActionResult(result_id="r_0001", execution_plan_id="", status="completed")

    with pytest.raises(ValueError, match="execution_plan_id"):
        run.promote(
            mode="transition",
            predicted_transition_id=predicted.transition_id,
            action_result=result,
        )
