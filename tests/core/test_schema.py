import pytest
import optagent
import optagent.core

from optagent.core import (
    ActionResult,
    DerivedRecord,
    ExecutionPlan,
    ObservedTransition,
    PredictionDAG,
    PredictionMatch,
    PredictionPlan,
    PredictedTransition,
    Requirement,
    StateContext,
    StateNode,
    StateSnapshot,
    TraceDAG,
)


def _requirement() -> Requirement:
    return Requirement(
        requirement_id="req_kernel",
        target_type="kernel",
        target_id="csc_linear",
    )


def _state(state_id: str, state_kind: str) -> StateNode:
    return StateNode(
        state_id=state_id,
        state_kind=state_kind,  # type: ignore[arg-type]
        snapshot=StateSnapshot(requirement=_requirement()),
    )


def test_observed_transition_keeps_plan_and_result_separate():
    source = _state("s_obs_0000", "observed")
    target = _state("s_obs_0001", "observed")
    plan = ExecutionPlan(
        plan_id="p_exec_0001",
        plan_kind="execution",
        from_observed_state_id=source.state_id,
        action_type="implementation",
        intent="try scoped dispatch",
        expected_observation={"small_shape": "faster"},
    )
    result = ActionResult(
        result_id="r_0001",
        execution_plan_id=plan.plan_id,
        status="completed",
        artifacts=("artifacts/p_exec_0001.patch",),
        metrics={"speedup": 1.12},
    )

    transition = ObservedTransition(
        transition_id="t_obs_0001",
        transition_kind="observed",
        execution_plan_id=plan.plan_id,
        from_observed_state_id=source.state_id,
        to_observed_state_id=target.state_id,
        action_result=result,
    )

    plan_data = plan.to_dict()
    transition_data = transition.to_dict()
    assert plan_data["expected_observation"]["small_shape"] == "faster"
    assert transition_data["action_result"]["metrics"]["speedup"] == 1.12
    assert transition_data["from_observed_state_id"] == "s_obs_0000"
    assert transition_data["to_observed_state_id"] == "s_obs_0001"
    assert transition_data["matched_predicted_transition_id"] is None
    assert transition_data["derived_records"] == []


def test_prediction_and_execution_plans_are_not_collapsed_into_public_plan_alias():
    assert not hasattr(optagent, "Plan")
    assert not hasattr(optagent.core, "Plan")


def test_observed_transition_stores_interpretations_as_derived_records():
    source = _state("s_obs_0000", "observed")
    target = _state("s_obs_0001", "observed")
    plan = ExecutionPlan(
        plan_id="p_exec_0001",
        plan_kind="execution",
        from_observed_state_id=source.state_id,
        action_type="verification",
        intent="run benchmark matrix",
    )
    result = ActionResult(
        result_id="r_0001",
        execution_plan_id=plan.plan_id,
        status="completed",
        raw_outputs=("raw/bench.txt",),
        metrics={"speedup": 1.18},
    )
    evidence = DerivedRecord(
        derived_id="d_0001",
        source_transition_id="t_obs_0001",
        derived_type="evidence",
        payload={
            "correctness": "passed",
            "speedup": 1.18,
        },
        generator="evaluator:benchmark_parser:v1",
        confidence=0.95,
    )
    decision = DerivedRecord(
        derived_id="d_0002",
        source_transition_id="t_obs_0001",
        derived_type="decision",
        payload={
            "status": "accepted",
            "reason": "speedup threshold met",
        },
        generator="promotion_gate:v1",
    )

    transition = ObservedTransition(
        transition_id="t_obs_0001",
        transition_kind="observed",
        execution_plan_id=plan.plan_id,
        from_observed_state_id=source.state_id,
        to_observed_state_id=target.state_id,
        action_result=result,
        derived_records=(evidence, decision),
    )

    data = transition.to_dict()
    assert data["action_result"]["raw_outputs"] == ["raw/bench.txt"]
    assert data["derived_records"][0]["derived_type"] == "evidence"
    assert data["derived_records"][0]["generator"] == "evaluator:benchmark_parser:v1"
    assert data["derived_records"][1]["payload"]["status"] == "accepted"


def test_state_context_points_to_dag_views_not_state_content():
    context = StateContext(
        current_state_id="s_obs_0001",
        trace_dag_id="trace_run_001",
        prediction_dag_id="prediction_run_001",
        current_depth=1,
        past_depth=2,
        future_depth=3,
        focus_transition_ids=("t_obs_0001", "t_pred_0002"),
    )

    data = context.to_dict()
    assert data["current_state_id"] == "s_obs_0001"
    assert data["past_depth"] == 2
    assert data["future_depth"] == 3
    assert data["focus_transition_ids"] == ["t_obs_0001", "t_pred_0002"]


def test_prediction_dag_allows_multiple_predicted_outcomes_per_plan():
    source = _state("s_obs_0000", "observed")
    predicted_root = StateNode(
        state_id="s_pred_0000",
        state_kind="predicted",
        snapshot=source.snapshot,
        anchor_observed_state_id=source.state_id,
    )
    success_state = _state("s_pred_0001", "predicted")
    regression_state = _state("s_pred_0002", "predicted")
    plan = PredictionPlan(
        plan_id="p_pred_0001",
        plan_kind="prediction",
        from_predicted_state_id=predicted_root.state_id,
        action_type="implementation",
        intent="try fused small-shape kernel",
    )

    prediction_dag = PredictionDAG(
        dag_id="prediction_run_001",
        anchor_observed_state_id=source.state_id,
        root_predicted_state_id=predicted_root.state_id,
    )
    prediction_dag.add_node(predicted_root, depth=0)
    prediction_dag.add_node(success_state, depth=1)
    prediction_dag.add_node(regression_state, depth=1)
    prediction_dag.add_plan(plan)
    prediction_dag.add_transition(
        PredictedTransition(
            transition_id="t_pred_0001a",
            transition_kind="predicted",
            parent_plan_id=plan.plan_id,
            parent_plan_kind=plan.plan_kind,
            from_state_id=predicted_root.state_id,
            outcome_id="success",
            outcome_label="small shape improves",
            predicted_result={"speedup": 1.15},
            predicted_state_delta={"knowledge": "small shapes are launch-bound"},
            to_predicted_state_id=success_state.state_id,
        )
    )
    prediction_dag.add_transition(
        PredictedTransition(
            transition_id="t_pred_0001b",
            transition_kind="predicted",
            parent_plan_id=plan.plan_id,
            parent_plan_kind=plan.plan_kind,
            from_state_id=predicted_root.state_id,
            outcome_id="regression",
            outcome_label="large shape regresses",
            predicted_result={"regression": "batch_size=64"},
            predicted_state_delta={"open_question": "narrow dispatch scope"},
            to_predicted_state_id=regression_state.state_id,
        )
    )

    assert prediction_dag.plan_ids_from_state(predicted_root.state_id) == ["p_pred_0001"]
    assert prediction_dag.predicted_transition_ids_for_plan(plan.plan_id) == [
        "t_pred_0001a",
        "t_pred_0001b",
    ]
    assert prediction_dag.future_transition_ids(predicted_root.state_id) == [
        "t_pred_0001a",
        "t_pred_0001b",
    ]
    assert prediction_dag.depth(1) == [success_state, regression_state]


def test_trace_dag_records_one_observed_transition_per_execution_plan():
    source = _state("s_obs_0000", "observed")
    observed = _state("s_obs_0001", "observed")
    plan = ExecutionPlan(
        plan_id="p_exec_0001",
        plan_kind="execution",
        from_observed_state_id=source.state_id,
        action_type="investigation",
        intent="profile shape matrix",
    )
    result = ActionResult(
        result_id="r_0001",
        execution_plan_id=plan.plan_id,
        status="completed",
        raw_outputs=("raw/profile.txt",),
    )
    transition = ObservedTransition(
        transition_id="t_obs_0001",
        transition_kind="observed",
        execution_plan_id=plan.plan_id,
        from_observed_state_id=source.state_id,
        to_observed_state_id=observed.state_id,
        action_result=result,
        matched_predicted_transition_id="t_pred_0001b",
        prediction_match=PredictionMatch(
            matched_predicted_transition_id="t_pred_0001b",
            match_status="compatible",
            prediction_error={"latency_delta": "smaller than expected"},
        ),
    )

    trace_dag = TraceDAG(dag_id="trace_run_001")
    trace_dag.add_node(source, depth=0)
    trace_dag.add_node(observed, depth=1)
    trace_dag.add_execution_plan(plan)
    trace_dag.append_transition(transition)

    assert trace_dag.plan_ids_from_state(source.state_id) == ["p_exec_0001"]
    assert trace_dag.past_transition_ids(observed.state_id) == ["t_obs_0001"]
    assert trace_dag.next_transition_ids(source.state_id) == ["t_obs_0001"]
    assert trace_dag.depth(1) == [observed]

    with pytest.raises(ValueError):
        trace_dag.append_transition(
            ObservedTransition(
                transition_id="t_obs_0002",
                transition_kind="observed",
                execution_plan_id=plan.plan_id,
                from_observed_state_id=source.state_id,
                to_observed_state_id=observed.state_id,
                action_result=result,
            )
        )
