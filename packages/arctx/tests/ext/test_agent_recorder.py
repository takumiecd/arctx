"""Tests for the harness-neutral SessionRecorder (arctx.ext.agents)."""

from __future__ import annotations

import arctx
from arctx.core.schema.requirements import Requirement
from arctx.ext.agents import SessionRecorder


def _recorder(handle, ws_id="ws_x", harness="my-harness"):
    return SessionRecorder(
        handle, lane_id=ws_id, user_id="agent", harness=harness
    )


def _handle():
    return arctx.init(
        Requirement(requirement_id="req_a", target_type="task", target_id="a"),
        run_id="run_agents",
    )


def test_recorder_is_usable_without_any_harness_event_format():
    handle = _handle()
    rec = _recorder(handle)

    rec.start({"model": "some-model"})
    p = rec.prompt("try the first hypothesis")
    a = rec.action("run_benchmark", {"variant": "A"}, {"elapsed_ms": 1200})
    end = rec.turn_end(kind="session_end", content={"reason": "done"})

    session = handle.run_graph.lanes["ws_x"]
    assert session.metadata["agent"] == {"harness": "my-harness", "model": "some-model"}

    prompt_payloads = handle.run_graph.payloads_for_step(p["step_id"])
    assert [pl.type for pl in prompt_payloads] == ["agent.prompt"]
    action_payloads = handle.run_graph.payloads_for_step(a["step_id"])
    assert [pl.type for pl in action_payloads] == ["agent.tool_use"]
    assert action_payloads[0].metadata == {"harness": "my-harness"}

    end_payloads = handle.run_graph.payloads_for_node(end["node_id"])
    assert [pl.type for pl in end_payloads] == ["agent.session_end"]
    assert end_payloads[0].content == {"reason": "done"}


def test_recorder_chains_and_sessions_stay_independent():
    handle = _handle()
    rec_a = _recorder(handle, ws_id="ws_a")
    rec_b = _recorder(handle, ws_id="ws_b", harness="other-harness")

    a1 = rec_a.prompt("a1")
    b1 = rec_b.prompt("b1")
    a2 = rec_a.action("tool", {}, "out")

    t_a1 = handle.run_graph.steps[a1["step_id"]]
    t_b1 = handle.run_graph.steps[b1["step_id"]]
    t_a2 = handle.run_graph.steps[a2["step_id"]]
    assert t_a1.input_node_ids == (handle.root_node_id,)
    assert t_b1.input_node_ids == (handle.root_node_id,)
    assert t_a2.input_node_ids == (a1["output_node_id"],)
    assert rec_a.tip() == a2["output_node_id"]
    assert rec_b.tip() == b1["output_node_id"]


def test_turn_end_without_activity_returns_none():
    handle = _handle()
    assert _recorder(handle).turn_end() is None
