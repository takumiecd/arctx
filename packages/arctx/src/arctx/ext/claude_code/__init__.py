"""Claude Code hooks adapter extension.

Maps Claude Code hook events onto ARCTX records so an agent session is
recorded into a run automatically, with no manual bookkeeping:

- one Claude Code session  -> one ``Lane`` (``ws_cc_<session_id>``)
- ``UserPromptSubmit``     -> ``Step`` + ``StepPayload(type="agent.prompt")``
- ``PostToolUse``          -> ``Step`` + ``StepPayload(type="agent.tool_use")``
- ``Stop`` / ``SessionEnd``-> ``NodePayload`` attached to the session tip

Only generic core payloads are used, so runs need no extension enablement
and every existing CLI surface (dump / export / TUI) renders the records.
"""

from __future__ import annotations

from arctx.ext.base import CliCommand, ExtensionBase
from arctx.ext.claude_code.adapter import (
    record_hook_event,
    session_tip,
    lane_id_for,
)


class ClaudeCodeExtension(ExtensionBase):
    """Extension for recording Claude Code sessions through hooks."""

    name = "claude-code"
    version = "0.1"
    description = "Integration with Claude Code AI agent."

    def cli_commands(self) -> list[CliCommand]:
        from arctx_cli.ext.claude_code import add_parser, cli_claude_code

        return [CliCommand(name=self.name, add_parser=add_parser, handler=cli_claude_code)]


__all__ = [
    "ClaudeCodeExtension",
    "record_hook_event",
    "session_tip",
    "lane_id_for",
]
