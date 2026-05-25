from stag.cli.commands.init import run_init_command
from stag.cli.commands.observe import run_observe_command
from stag.cli.commands.plan import run_plan_command
from stag.cli.commands.show import run_show_command


def test_basic_cli_flow_uses_transition_ids(tmp_path):
    store_dir = str(tmp_path)
    run_id = "run"
    root = run_init_command(
        requirement_id="req", target_type="code", target_id=None, run_id=run_id, store_dir=store_dir
    )["root_node_id"]
    transition = run_plan_command(
        run_id=run_id,
        input_node_ids=[root],
        action_type="analysis",
        intent="try",
        store_dir=store_dir,
    )["transition"]
    node = run_observe_command(
        run_id=run_id,
        transition_id=transition["transition_id"],
        status="completed",
        artifacts=None,
        raw_outputs=None,
        logs=None,
        metrics=None,
        errors=None,
        store_dir=store_dir,
    )["node"]

    shown = run_show_command(
        run_id=run_id,
        node_id=None,
        transition_id=transition["transition_id"],
        payload_id=None,
        with_payloads=True,
        outputs=True,
        store_dir=store_dir,
    )

    assert shown["transition"]["transition_id"] == transition["transition_id"]
    assert shown["output_nodes"][0]["node_id"] == node["node_id"]
