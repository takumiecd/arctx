from stag.cli.commands.init import run_init_command
from stag.cli.commands.migrate import run_migrate_command
from stag.cli.commands.plan import run_plan_command
from stag.storage.jsonl import JsonlRunStore


def test_migrate_preserves_transition_dag(tmp_path):
    src_dir = tmp_path / "jsonl"
    run_id = "run"
    root = run_init_command(
        requirement_id="req",
        target_type="code",
        target_id=None,
        run_id=run_id,
        store_dir=str(src_dir),
    )["root_node_id"]
    transition_id = run_plan_command(
        run_id=run_id,
        input_node_ids=[root],
        action_type="analysis",
        intent="try",
        store_dir=str(src_dir),
    )["transition"]["transition_id"]

    run_migrate_command(
        to="sqlite",
        store_dir=str(src_dir),
        run_id=run_id,
        all_runs=False,
        force=False,
    )

    assert transition_id in JsonlRunStore(src_dir).load_run(run_id).run_graph.transitions
