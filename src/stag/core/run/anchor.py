"""RunHandle.anchor implementation."""

from __future__ import annotations

from stag.core.schema.graph import Node
from stag.core.schema.payloads import PlanPayload, ResultPayload


def anchor_impl(
    self,
    from_node_id: str,
    label: str,
    *,
    metadata: dict | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> Node:
    """Create a lightweight scope anchor node from an existing node.

    An anchor is represented as a Transition with Plan/Result payloads and
    a generated output node tagged with metadata.kind="anchor".
    The output node can then be used as a shared branching point for experiments.
    """
    meta = dict(metadata or {})
    meta.setdefault("kind", "anchor")
    meta.setdefault("label", label)

    plan = PlanPayload(
        payload_id="pending",
        target_id="pending",
        intent=label,
        action_type="scope_refinement",
        metadata={"kind": "anchor", "label": label},
    )
    transition = self.plan([from_node_id], plan, user_id=user_id, work_session_id=work_session_id)

    result = ResultPayload(
        payload_id="pending",
        target_id="pending",
        status="completed",
        metadata=meta,
    )
    return self.observe(
        transition.transition_id,
        result,
        user_id=user_id,
        work_session_id=work_session_id,
    )
