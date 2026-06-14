"""RunHandle.add_step implementation."""

from __future__ import annotations

import dataclasses

from arctx.core.schema.graph import Node, Step
from arctx.core.schema.payloads import PayloadBase


def add_step_impl(
    self,
    input_node_ids: list[str] | tuple[str, ...],
    payload: PayloadBase,
    *,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> Step:
    """Create one Step from the given input nodes.

    The Step gets:
    - A freshly minted output Node.
    - A copy of *payload* with a new payload_id and the step's target_id.

    *payload* must be a step-targeting payload (target_kind="step").
    """
    if payload.target_kind != "step":
        raise ValueError(
            f"step() requires a step-targeting payload "
            f"(target_kind='step'), got {payload.target_kind!r}"
        )

    inputs = tuple(input_node_ids)
    for nid in inputs:
        self._ensure_active_node(nid)

    # Mint output node first (add_step validates it exists).
    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    step_id = self._next_id("t")
    step = Step(
        step_id=step_id,
        input_node_ids=inputs,
        output_node_id=output_node.node_id,
    )
    self.run_graph.add_step(step)

    cloned = _clone_payload(payload, self._next_id("pl"), step_id)
    self.run_graph.attach_payload(cloned)

    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="step_created",
        target_kind="step",
        target_id=step.step_id,
        created_records=(output_node.node_id, step_id, cloned.payload_id),
        summary=_payload_summary(payload),
    )
    return step


def _clone_payload(payload: PayloadBase, new_payload_id: str, new_target_id: str) -> PayloadBase:
    """Return a copy of payload with new payload_id and target_id."""
    if not dataclasses.is_dataclass(payload):
        raise TypeError(f"payload must be a dataclass, got {type(payload)!r}")
    # Build kwargs from all *init* fields, overriding payload_id and target_id.
    kwargs = {}
    for f in dataclasses.fields(payload):  # type: ignore[arg-type]
        if not f.init:
            continue
        val = getattr(payload, f.name)
        if f.name == "payload_id":
            kwargs[f.name] = new_payload_id
        elif f.name == "target_id":
            kwargs[f.name] = new_target_id
        else:
            kwargs[f.name] = val
    return type(payload)(**kwargs)


def _payload_summary(payload: PayloadBase) -> str | None:
    # Best-effort: look for a 'type' or 'intent' field.
    for attr in ("type", "intent"):
        val = getattr(payload, attr, None)
        if isinstance(val, str) and val:
            return val
    return None
