from stag.cli.commands.init import run_init_command
from stag.cli.commands.plan import run_plan_command
from stag.cli.commands.reachable import run_reachable_command


def test_reachable_reports_transitions(tmp_path):
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

    result = run_reachable_command(
        run_id=run_id, from_node=root, view_name=None, include_records=False, store_dir=store_dir
    )

    assert transition_id in result["transition_ids"]
