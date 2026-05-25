import stag
from stag.core.schema.payloads import PlanPayload, ResultPayload
from stag.core.schema.requirements import Requirement
from stag.storage.sqlite import SqliteRunStore


def _run():
    return stag.init(Requirement("req", "code", "target"), run_id="run")


def test_sqlite_round_trip_node_transition_edge_payload(tmp_path):
    store = SqliteRunStore(tmp_path)
    run = _run()
    transition = run.plan([run.root_node_id], PlanPayload("pending", "pending", "try"))
    node = run.observe(transition.transition_id, ResultPayload("pending", "pending", "completed"))

    store.save_run(run)
    loaded = store.load_run("run")

    assert transition.transition_id in loaded.run_graph.transitions
    assert node.node_id in loaded.run_graph.nodes
    assert len(loaded.run_graph.edges) == 2
    assert len(loaded.run_graph.payloads_for_transition(transition.transition_id)) == 2


def test_sqlite_save_after_incremental_mutation(tmp_path):
    store = SqliteRunStore(tmp_path)
    run = _run()
    store.save_run(run)

    transition = run.plan([run.root_node_id], PlanPayload("pending", "pending", "try"))
    store.save_run(run)

    loaded = store.load_run("run")
    assert transition.transition_id in loaded.run_graph.transitions
