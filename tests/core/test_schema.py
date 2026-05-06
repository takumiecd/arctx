from optagent.core import (
    ActionResult,
    ActionSpec,
    DerivedRecord,
    EvidenceTree,
    PlannedTransition,
    PredictionTree,
    Requirement,
    StateContext,
    StateNode,
    StateSnapshot,
    TransitionRecord,
)


def test_transition_record_keeps_plan_and_result_separate():
    requirement = Requirement(
        requirement_id="req_kernel",
        target_type="kernel",
        target_id="csc_linear",
    )
    source = StateNode(
        state_id="state_0000",
        snapshot=StateSnapshot(
            requirement=requirement,
            open_questions=("is small shape launch-bound?",),
        ),
        status="observed",
    )
    target = StateNode(
        state_id="state_0001",
        snapshot=StateSnapshot(
            requirement=requirement,
            open_questions=("large shape regression remains unexplained",),
        ),
        status="observed",
    )
    action = ActionSpec(
        action_id="action_0001",
        action_type="implementation",
        intent="try scoped dispatch",
        expected_observation={"small_shape": "faster"},
    )
    result = ActionResult(
        action_id=action.action_id,
        status="completed",
        artifacts=("artifacts/action_0001.patch",),
        metrics={"speedup": 1.12},
    )

    transition = TransitionRecord(
        transition_id="transition_0001",
        from_state_id=source.state_id,
        to_state_id=target.state_id,
        action_spec=action,
        action_result=result,
    )

    data = transition.to_dict()
    assert data["action_spec"]["expected_observation"]["small_shape"] == "faster"
    assert data["action_result"]["metrics"]["speedup"] == 1.12
    assert data["from_state_id"] == "state_0000"
    assert data["to_state_id"] == "state_0001"
    assert "observation" not in data
    assert data["derived_records"] == []


def test_transition_record_stores_interpretations_as_derived_records():
    requirement = Requirement(
        requirement_id="req_kernel",
        target_type="kernel",
        target_id="csc_linear",
    )
    source = StateNode(
        state_id="state_0000",
        snapshot=StateSnapshot(requirement=requirement),
        status="observed",
    )
    target = StateNode(
        state_id="state_0001",
        snapshot=StateSnapshot(requirement=requirement),
        status="observed",
    )
    action = ActionSpec(
        action_id="action_0001",
        action_type="verification",
        intent="run benchmark matrix",
    )
    result = ActionResult(
        action_id=action.action_id,
        status="completed",
        raw_outputs=("raw/bench.txt",),
        metrics={"speedup": 1.18},
    )
    evidence = DerivedRecord(
        derived_id="derived_0001",
        source_transition_id="transition_0001",
        derived_type="evidence",
        payload={
            "correctness": "passed",
            "speedup": 1.18,
        },
        generator="evaluator:benchmark_parser:v1",
        confidence=0.95,
    )
    decision = DerivedRecord(
        derived_id="derived_0002",
        source_transition_id="transition_0001",
        derived_type="decision",
        payload={
            "status": "accepted",
            "reason": "speedup threshold met",
        },
        generator="promotion_gate:v1",
    )

    transition = TransitionRecord(
        transition_id="transition_0001",
        from_state_id=source.state_id,
        to_state_id=target.state_id,
        action_spec=action,
        action_result=result,
        derived_records=(evidence, decision),
    )

    data = transition.to_dict()
    assert data["action_result"]["raw_outputs"] == ["raw/bench.txt"]
    assert data["derived_records"][0]["derived_type"] == "evidence"
    assert data["derived_records"][0]["generator"] == "evaluator:benchmark_parser:v1"
    assert data["derived_records"][1]["payload"]["status"] == "accepted"


def test_state_context_points_to_tree_views_not_state_content():
    context = StateContext(
        current_state_id="state_0001",
        evidence_tree_id="evidence_run_001",
        prediction_tree_id="prediction_run_001",
        current_depth=1,
        past_depth=2,
        future_depth=3,
        focus_transition_ids=("transition_0001", "planned_0002"),
    )

    data = context.to_dict()
    assert data["current_state_id"] == "state_0001"
    assert data["past_depth"] == 2
    assert data["future_depth"] == 3
    assert data["focus_transition_ids"] == ["transition_0001", "planned_0002"]


def test_trees_own_past_and_future_transition_indexes():
    requirement = Requirement(
        requirement_id="req_kernel",
        target_type="kernel",
        target_id="csc_linear",
    )
    source = StateNode(
        state_id="state_0000",
        snapshot=StateSnapshot(requirement=requirement),
        status="observed",
    )
    predicted = StateNode(
        state_id="state_predicted_0001",
        snapshot=StateSnapshot(requirement=requirement),
        status="predicted",
    )
    observed = StateNode(
        state_id="state_observed_0001",
        snapshot=StateSnapshot(requirement=requirement),
        status="observed",
    )
    action = ActionSpec(
        action_id="action_0001",
        action_type="investigation",
        intent="profile shape matrix",
    )

    prediction_tree = PredictionTree(tree_id="prediction_run_001")
    prediction_tree.add_node(source, depth=0)
    prediction_tree.add_node(predicted, depth=1)
    prediction_tree.add_transition(
        PlannedTransition(
            transition_id="planned_0001",
            from_state_id=source.state_id,
            to_predicted_state_id=predicted.state_id,
            action_spec=action,
            depth=1,
        )
    )

    evidence_tree = EvidenceTree(tree_id="evidence_run_001")
    evidence_tree.add_node(source, depth=0)
    evidence_tree.add_node(observed, depth=1)
    evidence_tree.append_transition(
        TransitionRecord(
            transition_id="transition_0001",
            from_state_id=source.state_id,
            to_state_id=observed.state_id,
            action_spec=action,
            action_result=ActionResult(
                action_id=action.action_id,
                status="completed",
                raw_outputs=("raw/profile.txt",),
            ),
        )
    )

    assert prediction_tree.future_transition_ids(source.state_id) == ["planned_0001"]
    assert evidence_tree.past_transition_ids(observed.state_id) == ["transition_0001"]
    assert evidence_tree.next_transition_ids(source.state_id) == ["transition_0001"]
    assert prediction_tree.depth(1) == [predicted]
