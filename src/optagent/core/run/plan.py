"""RunHandle.plan implementation."""

from __future__ import annotations

from optagent.core.schema.graph import InputTransition
from optagent.core.schema.payloads import PlanPayload


def plan_impl(
    self,
    input_node_ids: list[str] | tuple[str, ...],
    payload: PlanPayload,
    *,
    view: str = "main",
    user_id: str | None = None,
) -> InputTransition:
    """Create an InputTransition from one or more input nodes with a PlanPayload.

    All input_node_ids must be active (not in a cut subtree).
    """
    for nid in input_node_ids:
        self._ensure_active_node(nid)

    it_id = self._next_id("it")
    it = InputTransition(
        input_transition_id=it_id,
        input_node_ids=tuple(input_node_ids),
        metadata={**({"user_id": user_id} if user_id is not None else {})},
    )
    self.run_graph.add_input_transition(it)

    plan_payload = PlanPayload(
        payload_id=self._next_id("pl"),
        target_id=it_id,
        intent=payload.intent,
        action_type=payload.action_type,
        inputs=dict(payload.inputs),
        constraints=dict(payload.constraints),
        assumptions=tuple(payload.assumptions),
        safety_policy=dict(payload.safety_policy),
        metadata=dict(payload.metadata),
    )
    self.run_graph.attach_payload(plan_payload)

    v = self._get_view(view)
    v.input_transition_ids.add(it_id)
    v.payload_ids.add(plan_payload.payload_id)
    return it
