from optagent.core import ActionResult, ActionSpec, StateNode, TransitionRecord


def test_transition_record_keeps_plan_and_result_separate():
    source = StateNode(
        state_id="state_0000",
        depth=0,
        requirement_id="req_kernel",
        state_snapshot={"knowledge": ["baseline measured"]},
        status="observed",
    )
    target = StateNode(
        state_id="state_0001",
        depth=1,
        requirement_id="req_kernel",
        parent_state_ids=(source.state_id,),
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
