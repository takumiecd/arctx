from stag.cli.commands.init import run_init_command
from stag.cli.commands.observe import run_observe_command
from stag.cli.commands.plan import run_plan_command
from stag.storage.sqlite import SqliteRunStore


def test_sqlite_cli_flow_persists_transition_dag(tmp_path):
    (tmp_path / "config.json").write_text('{"storage": {"backend": "sqlite"}}\n')
    store_dir = str(tmp_path / "runs")
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
    node_id = run_observe_command(
        run_id=run_id,
        transition_id=transition_id,
        status="completed",
        artifacts=None,
        raw_outputs=None,
        logs=None,
        metrics=None,
        errors=None,
        store_dir=store_dir,
    )["node"]["node_id"]

    handle = SqliteRunStore(store_dir).load_run(run_id)
    assert transition_id in handle.run_graph.transitions
    assert node_id in handle.run_graph.nodes
