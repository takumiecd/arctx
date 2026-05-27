"""RunHandle.transition implementation."""

from __future__ import annotations

import dataclasses

from arctx.core.schema.graph import Node, Transition
from arctx.core.schema.payloads import PayloadBase


def transition_impl(
    self,
    input_node_ids: list[str] | tuple[str, ...],
    payload: PayloadBase,
    *,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> Transition:
    """Create one Transition from the given input nodes.

    The Transition gets:
    - A freshly minted output Node.
    - A copy of *payload* with a new payload_id and the transition's target_id.

    *payload* must be a transition-targeting payload (target_kind="transition").
    """
    if payload.target_kind != "transition":
        raise ValueError(
            f"transition() requires a transition-targeting payload "
            f"(target_kind='transition'), got {payload.target_kind!r}"
        )

    inputs = tuple(input_node_ids)
    for nid in inputs:
        self._ensure_active_node(nid)

    # Mint output node first (add_transition validates it exists).
    output_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(output_node)

    transition_id = self._next_id("t")
    transition = Transition(
        transition_id=transition_id,
        input_node_ids=inputs,
        output_node_id=output_node.node_id,
    )
    self.run_graph.add_transition(transition)

    cloned = _clone_payload(payload, self._next_id("pl"), transition_id)
    self.run_graph.attach_payload(cloned)

    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="transition_created",
        target_kind="transition",
        target_id=transition.transition_id,
        created_records=(output_node.node_id, transition_id, cloned.payload_id),
        summary=_payload_summary(payload),
    )
    return transition


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
