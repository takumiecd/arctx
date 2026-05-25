import stag
from stag.cli.append_batch import graph_counts
from stag.core.schema.payloads import PlanPayload, ResultPayload
from stag.core.schema.requirements import Requirement


def test_graph_counts_track_new_dag_records():
    run = stag.init(Requirement("req", "code", "target"), run_id="run")
    before = graph_counts(run)

    transition = run.plan([run.root_node_id], PlanPayload("pending", "pending", "try"))
    run.observe(transition.transition_id, ResultPayload("pending", "pending", "completed"))
    after = graph_counts(run)

    assert len(after["nodes"]) == len(before["nodes"]) + 1
    assert len(after["transitions"]) == len(before["transitions"]) + 1
    assert len(after["edges"]) == len(before["edges"]) + 2
    assert len(after["payloads"]) == len(before["payloads"]) + 2
