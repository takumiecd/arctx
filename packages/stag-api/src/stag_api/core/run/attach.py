"""RunHandle.attach implementation."""

from __future__ import annotations

from stag_api.core.schema.payloads import PayloadBase
from stag_api.core.run.transition import _clone_payload


def attach_impl(
    self,
    node_id: str,
    payload: PayloadBase,
    *,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> PayloadBase:
    """Attach a node-targeting payload to a node.

    *payload* must be a node-targeting payload (target_kind="node").
    Returns the attached payload (with a freshly minted payload_id).
    """
    if payload.target_kind != "node":
        raise ValueError(
            f"attach() requires a node-targeting payload "
            f"(target_kind='node'), got {payload.target_kind!r}"
        )
    if node_id not in self.run_graph.nodes:
        raise KeyError(f"unknown node_id: {node_id}")

    cloned = _clone_payload(payload, self._next_id("pl"), node_id)
    self.run_graph.attach_payload(cloned)
    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="payload_attached",
        target_kind="node",
        target_id=node_id,
        created_records=(cloned.payload_id,),
        summary=_node_payload_summary(cloned),
    )
    return cloned


def _node_payload_summary(payload: PayloadBase) -> str | None:
    for attr in ("type", "text"):
        val = getattr(payload, attr, None)
        if isinstance(val, str) and val:
            return val
    return None
