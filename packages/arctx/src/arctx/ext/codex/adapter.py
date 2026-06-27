"""Translate Codex hook events into SessionRecorder calls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from arctx.ext.agents import DEFAULT_CLIP_CHARS, SessionRecorder, clip, session_tip

__all__ = [
    "DEFAULT_CLIP_CHARS",
    "clip",
    "record_hook_event",
    "session_tip",
    "lane_id_for",
]

HARNESS = "codex"

_SESSION_METADATA_KEYS = (
    "session_id",
    "transcript_path",
    "agent_transcript_path",
    "cwd",
    "source",
    "model",
    "turn_id",
    "agent_type",
    "permission_mode",
)

_TYPE_TO_HOOK_EVENT = {
    "task_started": "SessionStart",
    "task_complete": "Stop",
    "agent-turn-complete": "Stop",
    "user_message": "UserPromptSubmit",
}


def lane_id_for(session_id: str) -> str:
    """Deterministic Lane id for one Codex session/thread."""
    return f"ws_codex_{session_id}"


def record_hook_event(
    handle,
    event: Mapping[str, Any],
    *,
    user_id: str,
    tools: Sequence[str] | None = None,
    clip_chars: int = DEFAULT_CLIP_CHARS,
) -> dict[str, Any] | None:
    """Record one Codex hook event into the run graph."""
    name = _event_name(event)
    session_id = _session_id(event)
    if not name or not session_id:
        return None

    recorder = SessionRecorder(
        handle,
        lane_id=lane_id_for(str(session_id)),
        user_id=user_id,
        harness=HARNESS,
        clip_chars=clip_chars,
    )

    if name == "SessionStart":
        metadata = {k: event[k] for k in _SESSION_METADATA_KEYS if k in event}
        return {"event": name, **recorder.start(metadata)}

    if name == "UserPromptSubmit":
        prompt = _prompt(event)
        if not prompt:
            return None
        return {"event": name, **recorder.prompt(str(prompt))}

    if name == "PostToolUse":
        tool_name = _tool_name(event)
        if not tool_name:
            return None
        if tools is not None and "*" not in tools and tool_name not in tools:
            return None
        result = recorder.action(
            str(tool_name),
            _first_present(event, ("tool_input", "input", "arguments")),
            _first_present(event, ("tool_output", "tool_response", "output", "result")),
        )
        return {"event": name, **result}

    if name in ("Stop", "SessionEnd", "SubagentStop"):
        content: dict[str, Any] = {}
        for key in ("reason", "last_assistant_message", "agent_type"):
            if event.get(key):
                content[key] = str(event[key])
        kind = "session_end" if name == "SessionEnd" else "stop"
        result = recorder.turn_end(kind=kind, content=content)
        if result is None:
            return None
        return {"event": name, **result}

    return None


def _event_name(event: Mapping[str, Any]) -> str | None:
    raw = event.get("hook_event_name") or event.get("event_name")
    if raw:
        return str(raw)
    event_type = event.get("type")
    if event_type:
        return _TYPE_TO_HOOK_EVENT.get(str(event_type))
    return None


def _session_id(event: Mapping[str, Any]) -> str | None:
    for key in ("session_id", "thread_id", "conversation_id"):
        value = event.get(key)
        if value:
            return str(value)
    return None


def _prompt(event: Mapping[str, Any]) -> Any:
    for key in ("prompt", "message", "input"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _tool_name(event: Mapping[str, Any]) -> str | None:
    for key in ("tool_name", "toolName", "name"):
        value = event.get(key)
        if value:
            return str(value)
    tool = event.get("tool")
    if isinstance(tool, Mapping) and tool.get("name"):
        return str(tool["name"])
    return None


def _first_present(event: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in event:
            return event[key]
    return None
