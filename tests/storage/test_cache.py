import stag
from stag.core.schema.payloads import PlanPayload
from stag.core.schema.requirements import Requirement
from stag.storage.jsonl import JsonlRunStore


def test_store_load_rebuilds_transition_edge_indexes(tmp_path):
    run = stag.init(Requirement("req", "code", "target"), run_id="run")
    transition = run.plan([run.root_node_id], PlanPayload("pending", "pending", "try"))

    store = JsonlRunStore(tmp_path)
    store.save_run(run)
    loaded = store.load_run("run")

    assert loaded.run_graph.transitions_from_node(run.root_node_id) == [transition.transition_id]
    assert loaded.run_graph.transition_inputs(transition.transition_id) == [run.root_node_id]
