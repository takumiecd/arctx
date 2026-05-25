import stag
from stag.core.run.dump import DumpOptions, dump
from stag.core.schema.payloads import PlanPayload, ResultPayload
from stag.core.schema.requirements import Requirement


def _run():
    return stag.init(Requirement("req", "code", "target"), run_id="run")


def test_dump_includes_node_transition_and_payloads():
    run = _run()
    transition = run.plan(
        [run.root_node_id],
        PlanPayload("pending", "pending", intent="try baseline"),
    )
    node = run.observe(
        transition.transition_id,
        ResultPayload("pending", "pending", status="completed", metrics={"score": 1.0}),
    )

    out = dump(run, "outline", DumpOptions())

    assert run.root_node_id in out
    assert node.node_id in out
    assert transition.transition_id in out
    assert "transitions=1" in out
