"""Tests for core lane membership and validation helpers."""

from __future__ import annotations

import arctx
from arctx.core.lanes import (
    lane_boundaries,
    lane_export_view,
    lane_membership,
    lane_root_candidates,
    lane_subgraph,
    validate_lanes,
)
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement


def _handle(run_id: str = "run_lanes"):
    return arctx.init(
        Requirement(requirement_id="r", target_type="task", target_id="t"),
        run_id=run_id,
    )


def _payload(handle, label: str = "step") -> StepPayload:
    return StepPayload(payload_id=handle._next_id("pl"), target_id="pending", type=label)


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
    seed = h.add_node(user_id="alice", work_session_id="lane_seed")

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
    first = h.add_node(user_id="alice", work_session_id="lane_math")
    second = h.add_node(user_id="alice", work_session_id="lane_math")

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
    h.ensure_lane(
        name="math",
        lane_id="lane_math",
        created_by="alice",
        metadata={"root_node_id": h.root_node_id},
    )
    stray = h.add_node(user_id="alice", work_session_id="lane_math")

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
    h.add_node(user_id="alice", work_session_id="default")

    issues = validate_lanes(h.run_graph, root_node_id=h.root_node_id)

    assert any(
        issue.code == "default_lane_membership" and issue.lane_id == "default"
        for issue in issues
    )


def test_validate_lanes_errors_when_producerless_node_is_not_run_or_lane_root():
    h = _handle()
    stray = h.add_node()

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
    )

    assert view["groups"][0]["lane_id"] == "lane_math"
    assert view["record_provenance"][step.step_id]["lane_id"] == "lane_math"
    assert view["record_provenance"][step.step_id]["membership_kind"] == "created"
    assert view["created_provenance"][step.step_id]["lane_id"] == "lane_math"
    assert view["lanes"][0]["work_session_id"] == "lane_math"
    assert view["work_sessions"][0]["work_session_id"] == "lane_math"
