"""Payload records for the command extension."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from arctx.core.schema.payloads import (
    PayloadBase,
    register_payload_class,
    register_payload_decoder,
)
from arctx.core.types import JSONValue


@dataclass(frozen=True)
class CommandRunPayload(PayloadBase):
    """External command execution result attached to a Step."""

    payload_id: str
    target_id: str
    command: tuple[str, ...]
    cwd: str
    exit_code: int
    duration_ms: int
    stdout: str = ""
    stderr: str = ""
    started_at: str = ""
    finished_at: str = ""
    truncated_stdout: bool = False
    truncated_stderr: bool = False
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["step"] = field(default="step", init=False)
    payload_type: str = field(default="command_run", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "payload_id": self.payload_id,
            "payload_type": self.payload_type,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "command": list(self.command),
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "truncated_stdout": self.truncated_stdout,
            "truncated_stderr": self.truncated_stderr,
            "metadata": dict(self.metadata),
        }


def _command_run_from_dict(data: dict[str, JSONValue]) -> CommandRunPayload:
    raw_command = data.get("command") or []
    return CommandRunPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        command=tuple(str(part) for part in raw_command),
        cwd=str(data.get("cwd", "")),
        exit_code=int(data.get("exit_code", 0)),
        duration_ms=int(data.get("duration_ms", 0)),
        stdout=str(data.get("stdout", "")),
        stderr=str(data.get("stderr", "")),
        started_at=str(data.get("started_at", "")),
        finished_at=str(data.get("finished_at", "")),
        truncated_stdout=bool(data.get("truncated_stdout", False)),
        truncated_stderr=bool(data.get("truncated_stderr", False)),
        metadata=dict(data.get("metadata") or {}),
    )


register_payload_class(CommandRunPayload)
register_payload_decoder("command_run", _command_run_from_dict)
