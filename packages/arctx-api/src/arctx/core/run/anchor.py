"""RunHandle.anchor implementation."""

from __future__ import annotations

from arctx.core.schema.graph import Node
from arctx.core.schema.payloads import TransitionPayload


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

    An anchor is a Transition with type="anchor" and a generated output node.
    The output node can then be used as a shared branching point for experiments.
    """
    meta = dict(metadata or {})
    meta.setdefault("kind", "anchor")
    meta.setdefault("label", label)

    payload = TransitionPayload(
        payload_id="pending",
        target_id="pending",
        type="anchor",
        content={"label": label},
        metadata=meta,
    )
    transition = self.transition(
        [from_node_id],
        payload,
        user_id=user_id,
        work_session_id=work_session_id,
    )
    return self.run_graph.nodes[transition.output_node_id]
