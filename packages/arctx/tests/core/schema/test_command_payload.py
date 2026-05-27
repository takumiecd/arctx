"""Tests for command extension payload schema."""

from __future__ import annotations

from arctx.core.schema.payloads import payload_from_dict
from arctx.ext.command.payloads import CommandRunPayload


def test_command_run_payload_roundtrip():
    payload = CommandRunPayload(
        payload_id="pl1",
        target_id="t1",
        command=("python", "-c", "print('ok')"),
        cwd="/tmp",
        exit_code=0,
        duration_ms=12,
        stdout="ok\n",
        stderr="",
        started_at="2026-05-27T00:00:00+00:00",
        finished_at="2026-05-27T00:00:01+00:00",
    )

    restored = payload_from_dict(payload.to_dict())

    assert isinstance(restored, CommandRunPayload)
    assert restored.command == payload.command
    assert restored.exit_code == 0
    assert restored.stdout == "ok\n"
