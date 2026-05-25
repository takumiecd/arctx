from stag.cli.commands.init import run_init_command
from stag.cli.commands.plan import run_plan_command
from stag.core.sync.local import sync_init, sync_pull, sync_push, sync_status
from stag.storage.jsonl import JsonlRunStore


def test_local_sync_pushes_transition_edge_records(tmp_path):
    store_dir = tmp_path / "runs"
    remote_dir = tmp_path / "remotes"
    run_id = "run"
    root = run_init_command(
        requirement_id="req",
        target_type="code",
        target_id=None,
        run_id=run_id,
        store_dir=str(store_dir),
    )["root_node_id"]
    transition_id = run_plan_command(
        run_id=run_id,
        input_node_ids=[root],
        action_type="analysis",
        intent="try",
        store_dir=str(store_dir),
    )["transition"]["transition_id"]
    handle = JsonlRunStore(store_dir).load_run(run_id)
    run_path = JsonlRunStore(store_dir).run_path(run_id)

    sync_init(
        handle=handle,
        run_path=run_path,
        remote="local",
        shared_run_id="shared",
        remote_dir=remote_dir,
        workspace_id="ws",
        actor_id="user",
    )
    pushed = sync_push(
        handle=handle,
        remote="local",
        shared_run_id="shared",
        remote_dir=remote_dir,
        workspace_id="ws",
        actor_id="user",
    )
    status = sync_status(
        handle=handle, remote="local", shared_run_id="shared", remote_dir=remote_dir
    )

    assert pushed["pushed_records"] > 0
    assert status["unpushed_records"] == 0
    assert transition_id in handle.run_graph.transitions


def test_local_sync_pull_accepts_transition_records(tmp_path):
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "dest"
    remote_dir = tmp_path / "remotes"
    run_id = "run"
    root = run_init_command(
        requirement_id="req",
        target_type="code",
        target_id=None,
        run_id=run_id,
        store_dir=str(source_dir),
    )["root_node_id"]
    transition_id = run_plan_command(
        run_id=run_id,
        input_node_ids=[root],
        action_type="analysis",
        intent="try",
        store_dir=str(source_dir),
    )["transition"]["transition_id"]
    source = JsonlRunStore(source_dir).load_run(run_id)
    sync_push(
        handle=source,
        remote="local",
        shared_run_id="shared",
        remote_dir=remote_dir,
        workspace_id="ws1",
        actor_id="user",
    )

    run_init_command(
        requirement_id="req",
        target_type="code",
        target_id=None,
        run_id=run_id,
        store_dir=str(dest_dir),
    )
    dest_store = JsonlRunStore(dest_dir)
    dest = dest_store.load_run(run_id)
    sync_pull(handle=dest, remote="local", shared_run_id="shared", remote_dir=remote_dir)

    assert transition_id in dest.run_graph.transitions
