"""SessionRecorder — the neutral layer harness adapters write through.

The recorder mutates an in-memory ``RunHandle`` only; persisting is the
caller's job. Payload types are harness-neutral (``agent.prompt``,
``agent.tool_use``, ``agent.stop``, ``agent.session_end``); the harness
name is recorded on payload metadata and on the WorkSession, never in the
type string. This is the data contract that makes runs readable across
harnesses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from arctx.core.cuts import is_active_node
from arctx.core.schema.payloads import NodePayload, StepPayload

# Default cap for each recorded string field. Tool outputs can be huge
# (full file reads, long command output); the graph stores a clipped form
# and the harness's own transcript keeps the full record.
DEFAULT_CLIP_CHARS = 2000


def session_tip(handle, work_session_id: str) -> str:
    """Return the node id this session should extend next.

    Derived at read time from work events: the output node of the most
    recent step created in this work session that is still active.
    Falls back to the run root, so the first prompt of each session fans
    out as a sibling branch off the root.
    """
    graph = handle.run_graph
    for event in reversed(graph.work_events):
        if event.work_session_id != work_session_id:
            continue
        if event.event_type != "step_created":
            continue
        step = graph.steps.get(event.target_id or "")
        if step is None:
            continue
        node_id = step.output_node_id
        if node_id in graph.nodes and is_active_node(graph, node_id):
            return node_id
    return handle.root_node_id


def clip(value: Any, *, limit: int = DEFAULT_CLIP_CHARS) -> Any:
    """Recursively clip long strings so payload content stays bounded."""
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return value[:limit] + f"…(+{len(value) - limit} chars)"
    if isinstance(value, Mapping):
        return {str(k): clip(v, limit=limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clip(v, limit=limit) for v in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return clip(str(value), limit=limit)


@dataclass
class SessionRecorder:
    """Record one agent session into a run with the neutral vocabulary.

    One recorder per (run, session). Each prompt/action extends the
    session's own tip, so parallel sessions land as sibling branches.
    """

    handle: Any
    work_session_id: str
    user_id: str
    harness: str
    clip_chars: int = DEFAULT_CLIP_CHARS

    def start(self, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Ensure the WorkSession exists, carrying harness metadata."""
        session_meta = {"agent": {"harness": self.harness, **dict(metadata or {})}}
        self.handle.ensure_work_session(
            user_id=self.user_id,
            work_session_id=self.work_session_id,
            metadata=session_meta,
        )
        return {"work_session_id": self.work_session_id}

    def prompt(self, text: str) -> dict[str, Any]:
        """Record a user prompt as a Step (``agent.prompt``)."""
        return self._step(
            "agent.prompt", {"prompt": clip(text, limit=self.clip_chars)}
        )

    def action(
        self,
        name: str,
        action_input: Any = None,
        action_output: Any = None,
    ) -> dict[str, Any]:
        """Record one tool/action execution as a Step (``agent.tool_use``)."""
        content = {
            "tool_name": name,
            "tool_input": clip(action_input, limit=self.clip_chars),
            "tool_output": clip(action_output, limit=self.clip_chars),
        }
        return self._step("agent.tool_use", content)

    def turn_end(
        self, *, kind: str = "stop", content: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Mark the end of a turn/session on the session tip.

        ``kind`` is "stop" or "session_end". Returns None when the session
        has no activity yet (nothing to mark).
        """
        tip = session_tip(self.handle, self.work_session_id)
        if tip == self.handle.root_node_id:
            return None
        attached = self.handle.attach(
            tip,
            NodePayload(
                payload_id="pending",
                target_id="pending",
                type=f"agent.{kind}",
                content=dict(content or {}),
                metadata={"harness": self.harness},
            ),
            user_id=self.user_id,
            work_session_id=self.work_session_id,
        )
        return {
            "work_session_id": self.work_session_id,
            "node_id": tip,
            "payload_id": attached.payload_id,
        }

    def tip(self) -> str:
        """Return the node this session would extend next."""
        return session_tip(self.handle, self.work_session_id)

    def _step(
        self, payload_type: str, content: dict[str, Any]
    ) -> dict[str, Any]:
        tip = session_tip(self.handle, self.work_session_id)
        step = self.handle.add_step(
            [tip],
            StepPayload(
                payload_id="pending",
                target_id="pending",
                type=payload_type,
                content=content,
                metadata={"harness": self.harness},
            ),
            user_id=self.user_id,
            work_session_id=self.work_session_id,
        )
        return {
            "work_session_id": self.work_session_id,
            "step_id": step.step_id,
            "output_node_id": step.output_node_id,
        }
