"""Translate Claude Code hook events into SessionRecorder calls.

This module is a thin harness adapter: it parses Claude Code's hook event
JSON (https://code.claude.com/docs/en/hooks) and forwards it to the
harness-neutral ``arctx.ext.agents.SessionRecorder``. All graph semantics
(tip derivation, payload vocabulary, clipping) live in the neutral layer;
a new harness adapter should need only a translation like this one.

The functions here mutate an in-memory ``RunHandle`` only; persisting the
mutation is the caller's job.
"""

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

HARNESS = "claude-code"

_SESSION_METADATA_KEYS = ("session_id", "transcript_path", "cwd", "source", "model")


def lane_id_for(session_id: str) -> str:
    """Deterministic Lane id for one Claude Code session."""
    return f"ws_cc_{session_id}"


def record_hook_event(
    handle,
    event: Mapping[str, Any],
    *,
    user_id: str,
    tools: Sequence[str] | None = None,
    clip_chars: int = DEFAULT_CLIP_CHARS,
) -> dict[str, Any] | None:
    """Record one hook event into the run graph.

    Returns a summary dict of what was recorded (with the originating hook
    event under ``"event"``), or None when the event is a no-op (unknown
    event, filtered tool, stop with no session activity).

    ``tools`` filters PostToolUse by tool name; None or ``"*"`` records
    every tool that arrives (the settings.json matcher is the primary
    filter — this is a second gate for direct invocations).
    """
    name = event.get("hook_event_name")
    session_id = event.get("session_id")
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
        prompt = event.get("prompt")
        if not prompt:
            return None
        return {"event": name, **recorder.prompt(str(prompt))}

    if name == "PostToolUse":
        tool_name = event.get("tool_name")
        if not tool_name:
            return None
        if tools is not None and "*" not in tools and tool_name not in tools:
            return None
        result = recorder.action(
            str(tool_name),
            event.get("tool_input"),
            event.get("tool_output", event.get("tool_response")),
        )
        return {"event": name, **result}

    if name in ("Stop", "SessionEnd"):
        content: dict[str, Any] = {}
        if name == "SessionEnd" and event.get("reason"):
            content["reason"] = str(event["reason"])
        kind = "stop" if name == "Stop" else "session_end"
        result = recorder.turn_end(kind=kind, content=content)
        if result is None:
            return None
        return {"event": name, **result}

    return None
