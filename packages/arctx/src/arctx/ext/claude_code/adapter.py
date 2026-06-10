"""Map Claude Code hook events onto ARCTX records.

The functions here mutate an in-memory ``RunHandle`` only; persisting the
mutation is the caller's job (the CLI hook command uses the same
append-or-save path as every other mutating command).

Hook event reference: https://code.claude.com/docs/en/hooks
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from arctx.core.cuts import is_active_node
from arctx.core.schema.payloads import NodePayload, TransitionPayload

# Default cap for each recorded string field. Tool outputs can be huge
# (full file reads, long command output); the graph stores a clipped form
# and the transcript_path on the WorkSession keeps the full record.
DEFAULT_CLIP_CHARS = 2000

_SESSION_METADATA_KEYS = ("session_id", "transcript_path", "cwd", "source", "model")


def work_session_id_for(session_id: str) -> str:
    """Deterministic WorkSession id for one Claude Code session."""
    return f"ws_cc_{session_id}"


def session_tip(handle, work_session_id: str) -> str:
    """Return the node id this session should extend next.

    Derived at read time from work events: the output node of the most
    recent transition created in this work session that is still active.
    Falls back to the run root, so the first prompt of each session fans
    out as a sibling branch off the root.
    """
    graph = handle.run_graph
    for event in reversed(graph.work_events):
        if event.work_session_id != work_session_id:
            continue
        if event.event_type != "transition_created":
            continue
        transition = graph.transitions.get(event.target_id or "")
        if transition is None:
            continue
        node_id = transition.output_node_id
        if node_id in graph.nodes and is_active_node(graph, node_id):
            return node_id
    return handle.root_node_id


def clip(value: Any, *, limit: int = DEFAULT_CLIP_CHARS) -> Any:
    """Recursively clip long strings so payload content stays bounded."""
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return value[:limit] + f"…(+{len(value) - limit} chars)"
    if isinstance(value, Mapping):
        return {str(k): clip(v, limit=limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clip(v, limit=limit) for v in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return clip(str(value), limit=limit)


def record_hook_event(
    handle,
    event: Mapping[str, Any],
    *,
    user_id: str,
    tools: Sequence[str] | None = None,
    clip_chars: int = DEFAULT_CLIP_CHARS,
) -> dict[str, Any] | None:
    """Record one hook event into the run graph.

    Returns a summary dict of what was recorded, or None when the event is
    a no-op (unknown event, filtered tool, stop with no session activity).

    ``tools`` filters PostToolUse by tool name; None or ``"*"`` records
    every tool that arrives (the settings.json matcher is the primary
    filter — this is a second gate for direct invocations).
    """
    name = event.get("hook_event_name")
    session_id = event.get("session_id")
    if not name or not session_id:
        return None
    ws_id = work_session_id_for(str(session_id))

    if name == "SessionStart":
        metadata = {
            "claude_code": {k: event[k] for k in _SESSION_METADATA_KEYS if k in event}
        }
        handle.ensure_work_session(
            user_id=user_id, work_session_id=ws_id, metadata=metadata
        )
        return {"event": name, "work_session_id": ws_id}

    if name == "UserPromptSubmit":
        prompt = event.get("prompt")
        if not prompt:
            return None
        return _record_transition(
            handle,
            ws_id,
            user_id=user_id,
            payload_type="claude_code.prompt",
            content={"prompt": clip(prompt, limit=clip_chars)},
            event_name=name,
        )

    if name == "PostToolUse":
        tool_name = event.get("tool_name")
        if not tool_name:
            return None
        if tools is not None and "*" not in tools and tool_name not in tools:
            return None
        content = {
            "tool_name": tool_name,
            "tool_input": clip(event.get("tool_input"), limit=clip_chars),
            "tool_output": clip(
                event.get("tool_output", event.get("tool_response")),
                limit=clip_chars,
            ),
        }
        return _record_transition(
            handle,
            ws_id,
            user_id=user_id,
            payload_type="claude_code.tool_use",
            content=content,
            event_name=name,
        )

    if name in ("Stop", "SessionEnd"):
        tip = session_tip(handle, ws_id)
        if tip == handle.root_node_id:
            return None
        content: dict[str, Any] = {}
        if name == "SessionEnd" and event.get("reason"):
            content["reason"] = str(event["reason"])
        payload_type = "claude_code.stop" if name == "Stop" else "claude_code.session_end"
        attached = handle.attach(
            tip,
            NodePayload(
                payload_id="pending",
                target_id="pending",
                type=payload_type,
                content=content,
            ),
            user_id=user_id,
            work_session_id=ws_id,
        )
        return {
            "event": name,
            "work_session_id": ws_id,
            "node_id": tip,
            "payload_id": attached.payload_id,
        }

    return None


def _record_transition(
    handle,
    ws_id: str,
    *,
    user_id: str,
    payload_type: str,
    content: dict[str, Any],
    event_name: str,
) -> dict[str, Any]:
    tip = session_tip(handle, ws_id)
    transition = handle.transition(
        [tip],
        TransitionPayload(
            payload_id="pending",
            target_id="pending",
            type=payload_type,
            content=content,
        ),
        user_id=user_id,
        work_session_id=ws_id,
    )
    return {
        "event": event_name,
        "work_session_id": ws_id,
        "transition_id": transition.transition_id,
        "output_node_id": transition.output_node_id,
    }
