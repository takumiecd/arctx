"""Tests for the Codex hooks adapter."""

from __future__ import annotations

import arctx
from arctx.core.schema.requirements import Requirement
from arctx.ext.codex import record_hook_event, session_tip, lane_id_for


def _handle():
    return arctx.init(
        Requirement(requirement_id="req_codex", target_type="task", target_id="codex"),
        run_id="run_codex",
    )


def _event(name: str, session_id: str = "s1", **extra) -> dict:
    return {"hook_event_name": name, "session_id": session_id, **extra}


def test_session_start_creates_lane_with_metadata():
    handle = _handle()
    result = record_hook_event(
        handle,
        _event(
            "SessionStart",
            transcript_path="/tmp/transcript.jsonl",
            cwd="/tmp/project",
            source="startup",
            model="gpt-5.5",
        ),
        user_id="codex",
    )

    ws_id = lane_id_for("s1")
    assert result == {"event": "SessionStart", "lane_id": ws_id}
    session = handle.run_graph.lanes[ws_id]
    assert session.user_id == "codex"
    assert session.metadata["agent"]["harness"] == "codex"
    assert session.metadata["agent"]["source"] == "startup"
    assert session.metadata["agent"]["model"] == "gpt-5.5"


def test_prompt_then_tool_use_chain_within_session():
    handle = _handle()
    prompt = record_hook_event(
        handle, _event("UserPromptSubmit", prompt="fix the bug"), user_id="codex"
    )
    assert prompt is not None

    tool = record_hook_event(
        handle,
        _event(
            "PostToolUse",
            tool_name="Bash",
            tool_input={"command": "pytest -q"},
            tool_output="1 passed",
        ),
        user_id="codex",
    )
    assert tool is not None
    tool_step = handle.run_graph.steps[tool["step_id"]]
    assert tool_step.input_node_ids == (prompt["output_node_id"],)

    payloads = handle.run_graph.payloads_for_step(tool["step_id"])
    assert [p.type for p in payloads] == ["agent.tool_use"]
    assert payloads[0].content["tool_input"] == {"command": "pytest -q"}
    assert payloads[0].metadata == {"harness": "codex"}


def test_type_aliases_from_codex_event_stream_are_supported():
    handle = _handle()
    start = record_hook_event(
        handle,
        {"type": "task_started", "thread_id": "t1", "model": "gpt-5.5"},
        user_id="codex",
    )
    prompt = record_hook_event(
        handle,
        {"type": "user_message", "thread_id": "t1", "message": "hello"},
        user_id="codex",
    )
    stop = record_hook_event(
        handle,
        {"type": "task_complete", "thread_id": "t1", "last_assistant_message": "done"},
        user_id="codex",
    )

    assert start == {"event": "SessionStart", "lane_id": "ws_codex_t1"}
    assert prompt is not None
    assert stop is not None


def test_tool_filter_and_stop_noop():
    handle = _handle()
    assert (
        record_hook_event(
            handle,
            _event("PostToolUse", tool_name="Read", tool_input={}),
            user_id="codex",
            tools=["Bash", "apply_patch"],
        )
        is None
    )
    assert record_hook_event(handle, _event("Stop"), user_id="codex") is None


def test_session_tip_skips_cut_branch():
    handle = _handle()
    first = record_hook_event(
        handle, _event("UserPromptSubmit", prompt="first"), user_id="codex"
    )
    handle.cut(first["output_node_id"], target_kind="node", reason="dead end")

    ws_id = lane_id_for("s1")
    assert session_tip(handle, ws_id) == handle.root_node_id

    second = record_hook_event(
        handle, _event("UserPromptSubmit", prompt="second"), user_id="codex"
    )
    step = handle.run_graph.steps[second["step_id"]]
    assert step.input_node_ids == (handle.root_node_id,)
