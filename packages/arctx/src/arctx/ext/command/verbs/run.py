"""RunHandle.command.run implementation."""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from arctx.core.schema.graph import Node, Step
from arctx.core.schema.work_helpers import latest_session_pointer, make_session_pointer_event
from arctx.ext.command.payloads import CommandRunPayload

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle


def run_impl(
    self: "RunHandle",
    *,
    command: list[str] | tuple[str, ...],
    cwd: str | Path | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
    max_output_chars: int = 20000,
) -> dict[str, object]:
    """Execute an external command and record the result as a step."""
    command_tuple = tuple(str(part) for part in command)
    if not command_tuple:
        raise ValueError("command must not be empty")
    if max_output_chars < 0:
        raise ValueError("max_output_chars must be >= 0")

    current_node_ids = _resolve_current_node_ids(self, work_session_id)
    for node_id in current_node_ids:
        self._ensure_active_node(node_id)

    resolved_cwd = Path(cwd or ".").resolve()

    started_at = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    result = subprocess.run(
        list(command_tuple),
        cwd=str(resolved_cwd),
        capture_output=True,
    )
    duration_ms = round((time.perf_counter() - start) * 1000)
    finished_at = datetime.now(timezone.utc).isoformat()

    stdout_raw = result.stdout.decode("utf-8", errors="replace")
    stderr_raw = result.stderr.decode("utf-8", errors="replace")
    stdout, truncated_stdout = _truncate(stdout_raw, max_output_chars)
    stderr, truncated_stderr = _truncate(stderr_raw, max_output_chars)

    if user_id is not None and work_session_id is not None:
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)

    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    step = Step(
        step_id=self._next_id("t"),
        input_node_ids=current_node_ids,
        output_node_id=output_node.node_id,
    )
    self.run_graph.add_step(step)

    payload = CommandRunPayload(
        payload_id=self._next_id("pl"),
        target_id=step.step_id,
        command=command_tuple,
        cwd=str(resolved_cwd),
        exit_code=result.returncode,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
        started_at=started_at,
        finished_at=finished_at,
        truncated_stdout=truncated_stdout,
        truncated_stderr=truncated_stderr,
    )
    self.run_graph.attach_payload(payload)

    if user_id is not None and work_session_id is not None:
        pointer = make_session_pointer_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            current_node_ids=(output_node.node_id,),
            current_branch=None,
        )
        self.run_graph.add_work_event(pointer)

    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="command_run",
        target_kind="step",
        target_id=step.step_id,
        created_records=(output_node.node_id, step.step_id, payload.payload_id),
        summary=" ".join(command_tuple),
        data={
            "command": list(command_tuple),
            "cwd": str(resolved_cwd),
            "exit_code": result.returncode,
            "duration_ms": duration_ms,
        },
    )

    return {
        "step": step,
        "output_node": output_node,
        "payload": payload,
        "exit_code": result.returncode,
    }


def _resolve_current_node_ids(
    handle: "RunHandle",
    work_session_id: str | None,
) -> tuple[str, ...]:
    if work_session_id is not None:
        pointer = latest_session_pointer(handle.run_graph, work_session_id)
        if pointer is not None:
            raw_node_ids = pointer.data.get("current_node_ids") or []
            return tuple(str(node_id) for node_id in raw_node_ids)
    return (handle.root_node_id,)


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit], True
