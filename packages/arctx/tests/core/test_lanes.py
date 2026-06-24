"""Tests for core lane membership and validation helpers."""

from __future__ import annotations

import pytest

import arctx
from arctx.core.lanes import (
    lane_boundaries,
    lane_export_view,
    lane_membership,
    lane_root_candidates,
    lane_subgraph,
    validate_lanes,
)
from arctx.core.schema.graph import Node
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement


def _handle(run_id: str = "run_lanes"):
    return arctx.init(
        Requirement(requirement_id="r", target_type="task", target_id="t"),
        run_id=run_id,
    )


def _payload(handle, label: str = "step") -> StepPayload:
    return StepPayload(payload_id=handle._next_id("pl"), target_id="pending", type=label)


def _seed_node(handle, *, work_session_id: str | None = None, user_id: str = "alice") -> Node:
    """Mint a producer-less Node low-level for lane-validation fixtures.

    Standalone nodes have no public verb anymore; they only arise from imported
    subgraphs. When *work_session_id* is given, record the matching ``node_added``
    work event so the node joins that lane (mirrors the old ``add_node`` verb).
    """
    node = Node(node_id=handle._next_id("n"))
    handle.run_graph.add_node(node)
    if work_session_id is not None:
        handle.record_work_event(
            user_id=user_id,
            work_session_id=work_session_id,
            event_type="node_added",
            target_kind="node",
            target_id=node.node_id,
            created_records=(node.node_id,),
        )
    return node


def test_lane_membership_groups_step_and_output_node():
    h = _handle()
    h.ensure_lane(name="math", lane_id="lane_math", created_by="alice")

    step = h.add_step(
        [h.root_node_id],
        _payload(h, "derive"),
        user_id="alice",
        work_session_id="lane_math",
    )

    membership = lane_membership(h.run_graph)

    assert membership.step_to_lane[step.step_id] == "lane_math"
    assert membership.node_to_lane[step.output_node_id] == "lane_math"
    assert membership.provenance[step.step_id].lane_name == "math"
    assert membership.groups[0].to_dict()["label"] == "math"


def test_lane_adoption_sets_current_membership_without_rewriting_creation():
    h = _handle()
    h.ensure_lane(name="seed", lane_id="lane_seed", created_by="alice")
    h.ensure_lane(name="math", lane_id="lane_math", created_by="alice")
    step = h.add_step(
        [h.root_node_id],
        _payload(h, "seed"),
        user_id="alice",
        work_session_id="lane_seed",
    )

    h.adopt_lane_records(
        "lane_math",
        [step.step_id, step.output_node_id],
        user_id="bob",
        mode="explicit",
        target_id=step.output_node_id,
        reason="responsibility cleanup",
    )

    membership = lane_membership(h.run_graph)

    assert membership.step_to_lane[step.step_id] == "lane_math"
    assert membership.node_to_lane[step.output_node_id] == "lane_math"
    assert membership.provenance[step.step_id].membership_kind == "adopted"
    assert membership.provenance[step.step_id].user_id == "bob"
    assert membership.created_provenance[step.step_id].lane_id == "lane_seed"
    assert membership.created_provenance[step.step_id].membership_kind == "created"


def test_lane_boundaries_are_derived_from_cross_lane_inputs():
    h = _handle()
    h.ensure_lane(name="math", lane_id="lane_math", created_by="alice")
    h.ensure_lane(name="experiment", lane_id="lane_exp", created_by="alice")
    math_step = h.add_step(
        [h.root_node_id],
        _payload(h, "math"),
        user_id="alice",
        work_session_id="lane_math",
    )
    exp_step = h.add_step(
        [math_step.output_node_id],
        _payload(h, "experiment"),
        user_id="alice",
        work_session_id="lane_exp",
    )

    boundaries = lane_boundaries(h.run_graph)

    assert len(boundaries) == 1
    assert boundaries[0].from_lane_id == "lane_math"
    assert boundaries[0].to_lane_id == "lane_exp"
    assert boundaries[0].step_id == exp_step.step_id


def test_lane_subgraph_returns_one_lane_records():
    h = _handle()
    h.ensure_lane(name="math", lane_id="lane_math", created_by="alice")
    step = h.add_step(
        [h.root_node_id],
        _payload(h, "math"),
        user_id="alice",
        work_session_id="lane_math",
    )

    subgraph = lane_subgraph(h.run_graph, "lane_math")

    assert subgraph["node_ids"] == (step.output_node_id,)
    assert subgraph["step_ids"] == (step.step_id,)


def test_validate_lanes_reports_output_lane_mismatch():
    h = _handle()
    h.ensure_lane(name="seed", lane_id="lane_seed", created_by="alice")
    h.ensure_lane(name="math", lane_id="lane_math", created_by="alice")
    seed = _seed_node(h, work_session_id="lane_seed")

    step = h.add_step(
        [h.root_node_id],
        _payload(h, "math"),
        output_node_id=seed.node_id,
        user_id="alice",
        work_session_id="lane_math",
    )

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert any(
        issue.code == "step_output_lane_mismatch" and issue.record_id == step.step_id
        for issue in issues
    )


def test_validate_lanes_reports_multiple_lane_roots():
    h = _handle()
    h.ensure_lane(name="math", lane_id="lane_math", created_by="alice")
    first = _seed_node(h, work_session_id="lane_math")
    second = _seed_node(h, work_session_id="lane_math")

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert set(lane_root_candidates(h.run_graph, "lane_math")) == {
        first.node_id,
        second.node_id,
    }
    assert any(
        issue.code == "multiple_lane_roots"
        and issue.lane_id == "lane_math"
        and issue.severity == "error"
        for issue in issues
    )


def test_validate_lanes_reports_records_unreachable_from_explicit_root():
    h = _handle()
    root = _seed_node(h)
    stray = _seed_node(h)
    h.ensure_lane(
        name="math",
        lane_id="lane_math",
        created_by="alice",
        metadata={"root_node_id": root.node_id},
    )
    h.record_work_event(
        user_id="alice",
        work_session_id="lane_math",
        event_type="lane_adopted",
        target_kind="subgraph",
        target_id=root.node_id,
        created_records=(),
        data={"record_ids": [root.node_id, stray.node_id], "mode": "fixture"},
    )

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert any(
        issue.code == "lane_node_unreachable_from_root"
        and issue.record_id == stray.node_id
        and issue.lane_id == "lane_math"
        for issue in issues
    )


def test_lane_root_candidates_treat_entry_step_output_as_root():
    h = _handle()
    h.ensure_lane(name="math", lane_id="lane_math", created_by="alice")
    h.ensure_lane(name="experiment", lane_id="lane_exp", created_by="alice")
    math = h.add_step(
        [h.root_node_id],
        _payload(h, "math"),
        user_id="alice",
        work_session_id="lane_math",
    )
    exp = h.add_step(
        [math.output_node_id],
        _payload(h, "experiment"),
        user_id="alice",
        work_session_id="lane_exp",
    )

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert lane_root_candidates(h.run_graph, "lane_exp") == (exp.output_node_id,)
    assert math.output_node_id not in lane_root_candidates(h.run_graph, "lane_exp")
    assert not any(issue.severity == "error" for issue in issues)


def test_validate_lanes_warns_about_default_lane_membership():
    h = _handle()
    _seed_node(h, work_session_id="default")

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert any(
        issue.code == "default_lane_membership" and issue.lane_id == "default"
        for issue in issues
    )


def test_run_root_is_not_a_lane_member_even_if_adopted():
    h = _handle()
    h.ensure_lane(name="default", lane_id="default", created_by="alice")
    h.record_work_event(
        user_id="alice",
        work_session_id="default",
        event_type="lane_adopted",
        target_kind="subgraph",
        target_id=h.root_node_id,
        created_records=(),
        data={"record_ids": [h.root_node_id], "mode": "legacy"},
    )

    membership = lane_membership(h.run_graph, root_node_id=h.root_node_id)
    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert h.root_node_id not in membership.node_to_lane
    assert h.root_node_id not in membership.provenance
    assert not any(group.lane_id == "default" for group in membership.groups)
    assert not any(issue.code == "default_lane_membership" for issue in issues)


def test_adopt_lane_records_rejects_run_root():
    h = _handle()
    h.ensure_lane(name="default", lane_id="default", created_by="alice")

    with pytest.raises(ValueError, match="run root"):
        h.adopt_lane_records(
            "default",
            [h.root_node_id],
            user_id="alice",
            mode="explicit",
            target_id=h.root_node_id,
        )


def test_adopt_lane_records_rejects_invalid_lane_roots():
    h = _handle()
    h.ensure_lane(name="math", lane_id="lane_math", created_by="alice")
    h.ensure_lane(name="experiment", lane_id="lane_exp", created_by="alice")
    math_root = h.add_step(
        [h.root_node_id],
        _payload(h, "math"),
        user_id="alice",
        work_session_id="lane_math",
    )
    h.add_step(
        [math_root.output_node_id],
        _payload(h, "experiment"),
        user_id="alice",
        work_session_id="lane_exp",
    )
    other = h.add_step(
        [math_root.output_node_id],
        _payload(h, "other"),
        user_id="alice",
        work_session_id="lane_math",
    )

    before = tuple(event.event_id for event in h.run_graph.work_events)
    with pytest.raises(ValueError, match="multiple_lane_roots"):
        h.adopt_lane_records(
            "lane_exp",
            [other.step_id, other.output_node_id],
            user_id="alice",
            mode="explicit",
            target_id=other.step_id,
        )

    assert tuple(event.event_id for event in h.run_graph.work_events) == before
    membership = lane_membership(h.run_graph, root_node_id=h.root_node_id)
    assert membership.step_to_lane[other.step_id] == "lane_math"
    assert membership.node_to_lane[other.output_node_id] == "lane_math"


def test_validate_lanes_errors_when_non_root_node_has_no_lane():
    h = _handle()
    node = _seed_node(h)

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert any(
        issue.code == "node_without_lane"
        and issue.record_id == node.node_id
        and issue.severity == "error"
        for issue in issues
    )


def test_validate_lanes_errors_when_step_has_no_lane():
    h = _handle()
    step = h.add_step(
        [h.root_node_id],
        _payload(h, "unowned"),
        user_id="alice",
        work_session_id=None,
    )

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert any(
        issue.code == "step_without_lane"
        and issue.record_id == step.step_id
        and issue.severity == "error"
        for issue in issues
    )


def test_validate_lanes_errors_when_lane_root_is_run_root():
    h = _handle()
    h.ensure_lane(
        name="math",
        lane_id="lane_math",
        created_by="alice",
        metadata={"root_node_id": h.root_node_id},
    )

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert lane_root_candidates(h.run_graph, "lane_math") == ()
    assert any(
        issue.code == "run_root_as_lane_root"
        and issue.record_id == h.root_node_id
        and issue.severity == "error"
        for issue in issues
    )


def test_validate_lanes_errors_when_producerless_node_is_not_run_or_lane_root():
    h = _handle()
    stray = _seed_node(h)

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert any(
        issue.code == "producerless_node_without_root_role"
        and issue.record_id == stray.node_id
        and issue.severity == "error"
        for issue in issues
    )


def test_lane_export_view_is_json_ready():
    h = _handle()
    h.ensure_lane(name="math", lane_id="lane_math", created_by="alice")
    step = h.add_step(
        [h.root_node_id],
        _payload(h, "math"),
        user_id="alice",
        work_session_id="lane_math",
    )
    payload_ids = set(h.run_graph.payloads)

    view = lane_export_view(
        h.run_graph,
        node_ids=set(h.run_graph.nodes),
        step_ids=set(h.run_graph.steps),
        payload_ids=payload_ids,
        root_node_id=h.root_node_id,
    )

    assert view["groups"][0]["lane_id"] == "lane_math"
    assert view["record_provenance"][step.step_id]["lane_id"] == "lane_math"
    assert view["record_provenance"][step.step_id]["membership_kind"] == "created"
    assert view["created_provenance"][step.step_id]["lane_id"] == "lane_math"
    assert view["lanes"][0]["work_session_id"] == "lane_math"
    assert view["work_sessions"][0]["work_session_id"] == "lane_math"
