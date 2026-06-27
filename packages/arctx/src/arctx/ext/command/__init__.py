"""Built-in command extension."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from arctx.ext.base import CliCommand, ExtensionBase

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle


@dataclass
class CommandNamespace:
    """Python API namespace for command extension verbs."""

    handle: "RunHandle"

    def run(self, **kwargs: Any) -> dict[str, object]:
        from arctx.ext.command.verbs.run import run_impl

        return run_impl(self.handle, **kwargs)


class CommandExtension(ExtensionBase):
    """Extension for recording external command execution as DAG steps."""

    name = "command"
    version = "0.1"
    description = "Command execution recording extension."

    def register_schema(self) -> None:
        import arctx.ext.command.payloads  # noqa: F401

    def register_verbs(self, handle: "RunHandle") -> None:
        if hasattr(handle, self.name):
            return
        setattr(handle, self.name, CommandNamespace(handle))

    def cli_commands(self) -> list[CliCommand]:
        from arctx_cli.ext.command import add_parser, cli_command

        return [CliCommand(name=self.name, add_parser=add_parser, handler=cli_command)]

    def default_aliases(self) -> dict[str, str]:
        return {"cmd": "command run"}


__all__ = ["CommandExtension", "CommandNamespace"]
