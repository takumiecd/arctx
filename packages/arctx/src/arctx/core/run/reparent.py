"""RunHandle.reparent implementation.

Append-only re-parent: fix a node that was derived from the wrong inputs without
losing its descendant subtree. A new producing Step (new inputs -> the same
output node) is appended and the node's previously-active producing Step is cut,
so the node keeps exactly one active producer. The mistaken lineage stays
recorded (inactive) rather than being deleted.
"""

from __future__ import annotations

from arctx.core.run.step import _clone_payload, _payload_summary
from arctx.core.schema.graph import Step
from arctx.core.schema.payloads import PayloadBase


def reparent_impl(
    self,
    node_id: str,
    new_input_node_ids: list[str] | tuple[str, ...],
    payload: PayloadBase,
    *,
    reason: str | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> Step:
    """Re-parent *node_id* onto *new_input_node_ids* (append-only).

    Appends a new producing Step (``new_input_node_ids`` -> ``node_id``) and cuts
    the node's previously-active producing Step. The node ends with exactly one
    active producer (the new Step) and its descendants are preserved.

    *payload* must be a step-targeting payload (it annotates the new Step).
    Keep the new inputs in the same lane as *node_id* to stay lane-valid.
    """
    if payload.target_kind != "step":
        raise ValueError(
            f"reparent() requires a step-targeting payload "
            f"(target_kind='step'), got {payload.target_kind!r}"
        )
    if node_id not in self.run_graph.nodes:
        raise KeyError(f"unknown node_id: {node_id}")
    self._ensure_active_node(node_id)

    inputs = tuple(new_input_node_ids)
    if not inputs:
        raise ValueError("reparent() requires at least one input node")
    for nid in inputs:
        if nid not in self.run_graph.nodes:
            raise KeyError(f"unknown input_node_id: {nid}")
        self._ensure_active_node(nid)
    if node_id in inputs:
        raise ValueError(f"node {node_id!r} cannot be its own input")
    for nid in inputs:
        if node_id in self.run_graph.ancestors_of(nid):
            raise ValueError(
                f"re-parenting {node_id!r} onto {nid!r} would create a cycle "
                f"(it is an ancestor of {nid!r})"
            )

    # The producer to retire (the single active one, by invariant). May be None
    # for a producer-less node (then this just gives the node a parent).
    old_producer = self.run_graph.step_to_node(node_id)

    step_id = self._next_id("t")
    step = Step(step_id=step_id, input_node_ids=inputs, output_node_id=node_id)
    self.run_graph.add_step(step)

    cloned = _clone_payload(payload, self._next_id("pl"), step_id)
    self.run_graph.attach_payload(cloned)
    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="step_created",
        target_kind="step",
        target_id=step_id,
        created_records=(step_id, cloned.payload_id),
        summary=_payload_summary(payload),
    )

    if old_producer is not None:
        self.cut(
            old_producer,
            target_kind="step",
            reason=reason or f"reparented {node_id}",
            user_id=user_id,
            work_session_id=work_session_id,
        )

    return step
