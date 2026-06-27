"""Codex hooks adapter extension."""

from __future__ import annotations

from arctx.ext.base import CliCommand, ExtensionBase
from arctx.ext.codex.adapter import (
    record_hook_event,
    session_tip,
    lane_id_for,
)


class CodexExtension(ExtensionBase):
    """Extension for recording Codex sessions through hooks."""

    name = "codex"
    version = "0.1"
    description = "Integration with Codex AI agent."

    def cli_commands(self) -> list[CliCommand]:
        from arctx_cli.ext.codex import add_parser, cli_codex

        return [CliCommand(name=self.name, add_parser=add_parser, handler=cli_codex)]


__all__ = ["CodexExtension", "record_hook_event", "session_tip", "lane_id_for"]
