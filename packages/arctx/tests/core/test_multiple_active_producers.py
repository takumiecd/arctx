"""A node with two active producers must not be silent.

`reparent` keeps at most one producing Step active — that is what keeps the
active subgraph a tree. Nothing checked it at read time, so a run that reached
the broken state reported a merged lineage that never happened while `arctx
lane validate` and `arctx doctor` both said healthy.

Two routes get there and neither is exotic: concurrent writers (validation runs
outside the run lock, so two `reparent` calls both pass the guard) and a git
merge of two branches that each re-parented the same node. This is a detector,
not a preventer: it covers both routes and makes the state loud.
"""

from __future__ import annotations

from arctx import init
from arctx.core.cuts import nodes_with_multiple_active_producers
from arctx.core.lanes import validate_lanes
from arctx.core.schema.graph import Step
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement


def _tp() -> StepPayload:
    return StepPayload(payload_id="_", target_id="_", type="note")


def _run():
    handle = init(Requirement(requirement_id="r", target_type="task", target_id="t"))
    handle.ensure_lane(user_id="u", lane_id="L")
    return handle


def test_a_healthy_run_reports_nothing():
    handle = _run()
    kw = dict(user_id="u", lane_id="L")
    a = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    handle.add_step([a], _tp(), **kw)
    assert nodes_with_multiple_active_producers(handle.run_graph) == []


def test_reparent_alone_stays_healthy():
    """The normal re-parent leaves the old producer explicitly cut."""
    handle = _run()
    kw = dict(user_id="u", lane_id="L")
    a = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    b = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    step = handle.add_step([a], _tp(), **kw)
    handle.reparent(step.output_node_id, [b], _tp(), **kw)
    assert nodes_with_multiple_active_producers(handle.run_graph) == []


def test_two_active_producers_are_detected():
    handle = _run()
    kw = dict(user_id="u", lane_id="L")
    a = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    b = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    step = handle.add_step([a], _tp(), **kw)
    target = step.output_node_id

    # What a lost race (or a union merge of two re-parents) leaves behind: a
    # second producing Step for the same node, with neither one cut.
    rogue = Step(
        step_id=handle._next_id("t"),
        input_node_ids=(b,),
        output_node_id=target,
        metadata={},
    )
    handle.run_graph.add_step(rogue)

    broken = nodes_with_multiple_active_producers(handle.run_graph)
    assert [node_id for node_id, _ in broken] == [target]
    assert set(broken[0][1]) == {step.step_id, rogue.step_id}


def test_validate_lanes_surfaces_it_with_the_repair_command():
    handle = _run()
    kw = dict(user_id="u", lane_id="L")
    a = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    b = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    step = handle.add_step([a], _tp(), **kw)
    handle.run_graph.add_step(
        Step(
            step_id=handle._next_id("t"),
            input_node_ids=(b,),
            output_node_id=step.output_node_id,
            metadata={},
        )
    )

    issues = validate_lanes(handle.run_graph, root_node_id=handle.root_node_id)
    codes = [issue.code for issue in issues]
    assert "multiple_active_producers" in codes
    message = next(i.message for i in issues if i.code == "multiple_active_producers")
    assert "arctx cut step" in message


def test_cutting_the_duplicate_clears_it():
    handle = _run()
    kw = dict(user_id="u", lane_id="L")
    a = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    b = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    step = handle.add_step([a], _tp(), **kw)
    rogue_id = handle._next_id("t")
    handle.run_graph.add_step(
        Step(
            step_id=rogue_id,
            input_node_ids=(b,),
            output_node_id=step.output_node_id,
            metadata={},
        )
    )
    assert nodes_with_multiple_active_producers(handle.run_graph)

    handle.cut(rogue_id, target_kind="step", reason="duplicate producer", **kw)
    assert nodes_with_multiple_active_producers(handle.run_graph) == []


def test_a_cut_node_is_not_reported():
    """Cutting the node is how you retire a dead end.

    Reporting a retired branch would leave `arctx doctor` pointing at a problem
    the user already resolved, with no append-only way to clear it.
    """
    handle = _run()
    kw = dict(user_id="u", lane_id="L")
    a = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    b = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    step = handle.add_step([a], _tp(), **kw)
    handle.run_graph.add_step(
        Step(
            step_id=handle._next_id("t"),
            input_node_ids=(b,),
            output_node_id=step.output_node_id,
            metadata={},
        )
    )
    assert nodes_with_multiple_active_producers(handle.run_graph)

    handle.cut(step.output_node_id, target_kind="node", reason="dead end", **kw)
    assert nodes_with_multiple_active_producers(handle.run_graph) == []
