"""Tests for the Claude Code hooks adapter (arctx.ext.claude_code)."""

from __future__ import annotations

import arctx
from arctx.core.schema.requirements import Requirement
from arctx.ext.claude_code import record_hook_event, session_tip, work_session_id_for
from arctx.ext.claude_code.adapter import clip


def _handle():
    return arctx.init(
        Requirement(requirement_id="req_cc", target_type="task", target_id="cc"),
        run_id="run_cc",
    )


def _event(name: str, session_id: str = "s1", **extra) -> dict:
    return {"hook_event_name": name, "session_id": session_id, **extra}


def test_session_start_creates_work_session_with_metadata():
    handle = _handle()
    result = record_hook_event(
        handle,
        _event(
            "SessionStart",
            transcript_path="/tmp/transcript.jsonl",
            cwd="/tmp/project",
            source="startup",
            model="claude-sonnet-4-6",
        ),
        user_id="claude-code",
    )

    ws_id = work_session_id_for("s1")
    assert result == {"event": "SessionStart", "work_session_id": ws_id}
    session = handle.run_graph.work_sessions[ws_id]
    assert session.user_id == "claude-code"
    assert session.metadata["claude_code"]["source"] == "startup"
    assert session.metadata["claude_code"]["model"] == "claude-sonnet-4-6"


def test_prompt_then_tool_use_chain_within_session():
    handle = _handle()
    prompt = record_hook_event(
        handle, _event("UserPromptSubmit", prompt="fix the bug"), user_id="claude-code"
    )
    assert prompt is not None
    transition = handle.run_graph.transitions[prompt["transition_id"]]
    assert transition.input_node_ids == (handle.root_node_id,)

    tool = record_hook_event(
        handle,
        _event(
            "PostToolUse",
            tool_name="Bash",
            tool_input={"command": "pytest -q"},
            tool_output="1 passed",
        ),
        user_id="claude-code",
    )
    assert tool is not None
    tool_transition = handle.run_graph.transitions[tool["transition_id"]]
    assert tool_transition.input_node_ids == (prompt["output_node_id"],)

    payloads = handle.run_graph.payloads_for_transition(tool["transition_id"])
    assert [p.type for p in payloads] == ["claude_code.tool_use"]
    assert payloads[0].content["tool_input"] == {"command": "pytest -q"}
    assert payloads[0].content["tool_output"] == "1 passed"


def test_parallel_sessions_become_sibling_branches():
    handle = _handle()
    a = record_hook_event(
        handle, _event("UserPromptSubmit", session_id="sA", prompt="a"), user_id="u"
    )
    b = record_hook_event(
        handle, _event("UserPromptSubmit", session_id="sB", prompt="b"), user_id="u"
    )

    ta = handle.run_graph.transitions[a["transition_id"]]
    tb = handle.run_graph.transitions[b["transition_id"]]
    assert ta.input_node_ids == (handle.root_node_id,)
    assert tb.input_node_ids == (handle.root_node_id,)


def test_tool_filter_skips_unlisted_tools():
    handle = _handle()
    result = record_hook_event(
        handle,
        _event("PostToolUse", tool_name="Read", tool_input={}),
        user_id="u",
        tools=["Bash", "Edit"],
    )
    assert result is None
    assert len(handle.run_graph.transitions) == 0

    wildcard = record_hook_event(
        handle,
        _event("PostToolUse", tool_name="Read", tool_input={}),
        user_id="u",
        tools=["*"],
    )
    assert wildcard is not None


def test_stop_attaches_payload_to_session_tip():
    handle = _handle()
    prompt = record_hook_event(
        handle, _event("UserPromptSubmit", prompt="p"), user_id="u"
    )
    stop = record_hook_event(handle, _event("Stop"), user_id="u")

    assert stop is not None
    assert stop["node_id"] == prompt["output_node_id"]
    payloads = handle.run_graph.payloads_for_node(stop["node_id"])
    assert "claude_code.stop" in [p.type for p in payloads]


def test_stop_without_activity_is_noop():
    handle = _handle()
    assert record_hook_event(handle, _event("Stop"), user_id="u") is None
    assert record_hook_event(handle, _event("SessionEnd"), user_id="u") is None
    assert len(handle.run_graph.payloads) == 0


def test_session_tip_skips_cut_branch():
    handle = _handle()
    first = record_hook_event(
        handle, _event("UserPromptSubmit", prompt="first"), user_id="u"
    )
    handle.cut(first["output_node_id"], target_kind="node", reason="dead end")

    ws_id = work_session_id_for("s1")
    assert session_tip(handle, ws_id) == handle.root_node_id

    second = record_hook_event(
        handle, _event("UserPromptSubmit", prompt="second"), user_id="u"
    )
    transition = handle.run_graph.transitions[second["transition_id"]]
    assert transition.input_node_ids == (handle.root_node_id,)


def test_unknown_or_incomplete_events_are_noops():
    handle = _handle()
    assert record_hook_event(handle, {}, user_id="u") is None
    assert record_hook_event(handle, _event("PreCompact"), user_id="u") is None
    assert record_hook_event(handle, _event("UserPromptSubmit"), user_id="u") is None
    assert record_hook_event(handle, _event("PostToolUse"), user_id="u") is None


def test_clip_bounds_long_strings_recursively():
    long = "x" * 5000
    clipped = clip({"out": long, "nested": [long, 7, None]}, limit=100)
    assert clipped["out"].startswith("x" * 100)
    assert "+4900 chars" in clipped["out"]
    assert "+4900 chars" in clipped["nested"][0]
    assert clipped["nested"][1] == 7
    assert clipped["nested"][2] is None
