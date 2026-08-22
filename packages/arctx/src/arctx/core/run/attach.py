"""RunHandle.attach implementation."""

from __future__ import annotations

from arctx.core.run.step import _clone_payload
from arctx.core.schema.payloads import PayloadBase


def attach_impl(
    self,
    target_id: str,
    payload: PayloadBase,
    *,
    user_id: str | None = None,
    lane_id: str | None = None,
) -> PayloadBase:
    """Attach a payload to an existing Node or Step.

    The payload's own ``target_kind`` decides which record it lands on: a
    node-targeting payload attaches to a Node, a step-targeting one to a
    Step. A record can carry any number of payloads — attaching never
    creates a Step or a Node, so several annotations (several trial rows,
    say) can share one graph record instead of growing the graph.

    Returns the attached payload (with a freshly minted payload_id).
    """
    kind = payload.target_kind
    if kind == "node":
        if target_id not in self.run_graph.nodes:
            raise KeyError(f"unknown node_id: {target_id}")
    elif kind == "step":
        if target_id not in self.run_graph.steps:
            raise KeyError(f"unknown step_id: {target_id}")
    else:
        raise ValueError(
            f"attach() requires a node- or step-targeting payload, "
            f"got target_kind={kind!r}"
        )

    cloned = _clone_payload(payload, self._next_id("pl"), target_id)
    self.run_graph.attach_payload(cloned)
    self.record_work_event(
        user_id=user_id,
        lane_id=lane_id,
        event_type="payload_attached",
        target_kind=kind,
        target_id=target_id,
        created_records=(cloned.payload_id,),
        summary=_payload_summary(cloned),
    )
    return cloned


def _payload_summary(payload: PayloadBase) -> str | None:
    for attr in ("type", "title", "text"):
        val = getattr(payload, attr, None)
        if isinstance(val, str) and val:
            return val
    return payload.payload_type
