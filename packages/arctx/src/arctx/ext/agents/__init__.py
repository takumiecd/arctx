"""Harness-neutral agent session recording.

``SessionRecorder`` is the standard vocabulary for recording an agent
session into a run: session start, prompt, action (tool use), turn end.
Harness adapters (``arctx.ext.claude_code``, future Codex/Cursor adapters)
translate their native event formats into these calls; everything they
write shares the neutral ``agent.*`` payload types, so cross-harness
consumers read one vocabulary and the harness name lives in metadata.
"""

from __future__ import annotations

from arctx.ext.agents.recorder import (
    DEFAULT_CLIP_CHARS,
    SessionRecorder,
    clip,
    session_tip,
)

__all__ = ["DEFAULT_CLIP_CHARS", "SessionRecorder", "clip", "session_tip"]
