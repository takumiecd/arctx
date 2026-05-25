from stag.cli.commands.cut import run_cut_command
from stag.cli.commands.init import run_init_command
from stag.cli.commands.plan import run_plan_command
from stag.core.cuts import is_inactive_transition
from stag.storage.jsonl import JsonlRunStore


def test_cut_transition_appends_cut_payload(tmp_path):
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

    cut = run_cut_command(
        run_id=run_id,
        target_id=transition_id,
        target_kind="transition",
        reason="undo",
        store_dir=store_dir,
    )["cut"]

    handle = JsonlRunStore(store_dir).load_run(run_id)
    assert cut["target_kind"] == "transition"
    assert is_inactive_transition(handle.run_graph, transition_id)
