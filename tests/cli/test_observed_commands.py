from stag.cli.commands.init import run_init_command
from stag.cli.commands.observe import run_observe_command
from stag.cli.commands.plan import run_plan_command
from stag.storage.jsonl import JsonlRunStore


def test_observe_adds_result_node_and_payload(tmp_path):
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

    node = run_observe_command(
        run_id=run_id,
        transition_id=transition_id,
        status="completed",
        artifacts=None,
        raw_outputs=None,
        logs=None,
        metrics={"score": 1.0},
        errors=None,
        store_dir=store_dir,
    )["node"]

    handle = JsonlRunStore(store_dir).load_run(run_id)
    assert node["node_id"] in handle.run_graph.transition_outputs(transition_id)
    assert len(handle.run_graph.payloads_for_transition(transition_id, payload_type="result")) == 1
