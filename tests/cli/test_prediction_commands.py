from stag.cli.commands.init import run_init_command
from stag.cli.commands.plan import run_plan_command
from stag.cli.commands.predict import run_predict_command
from stag.storage.jsonl import JsonlRunStore


def test_predict_adds_output_nodes_and_prediction_payloads(tmp_path):
    store_dir = str(tmp_path)
    run_id = "run"
    root = run_init_command(
        requirement_id="req", target_type="code", target_id=None, run_id=run_id, store_dir=store_dir
    )["root_node_id"]
    transition_id = run_plan_command(
        run_id=run_id,
        input_node_ids=[root],
        action_type="analysis",
        intent="try",
        store_dir=store_dir,
    )["transition"]["transition_id"]

    result = run_predict_command(
        run_id=run_id, transition_id=transition_id, max_outcomes=3, store_dir=store_dir
    )

    handle = JsonlRunStore(store_dir).load_run(run_id)
    assert len(result["nodes"]) == 3
    assert len(handle.run_graph.transition_outputs(transition_id)) == 3
    assert (
        len(handle.run_graph.payloads_for_transition(transition_id, payload_type="prediction")) == 3
    )
