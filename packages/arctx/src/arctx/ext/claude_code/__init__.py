"""Claude Code hooks adapter.

Maps Claude Code hook events onto ARCTX records so an agent session is
recorded into a run automatically, with no manual bookkeeping:

- one Claude Code session  -> one ``WorkSession`` (``ws_cc_<session_id>``)
- ``UserPromptSubmit``     -> ``Transition`` + ``TransitionPayload(type="claude_code.prompt")``
- ``PostToolUse``          -> ``Transition`` + ``TransitionPayload(type="claude_code.tool_use")``
- ``Stop`` / ``SessionEnd``-> ``NodePayload`` attached to the session tip

Only generic core payloads are used, so runs need no extension enablement
and every existing CLI surface (dump / export / TUI) renders the records.
"""

from __future__ import annotations

from arctx.ext.claude_code.adapter import (
    record_hook_event,
    session_tip,
    work_session_id_for,
)

__all__ = ["record_hook_event", "session_tip", "work_session_id_for"]
