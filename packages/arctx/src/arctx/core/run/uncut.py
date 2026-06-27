"""RunHandle.uncut implementation.

Append-only reversal of a cut. Appends an :class:`UncutPayload` that supersedes
the target's most recent cut; the cut itself is never deleted. Effective cut
state is recomputed at read time (see :mod:`arctx.core.cuts`).
"""

from __future__ import annotations

from typing import Literal

from arctx.core.cuts import cut_node_ids, cut_step_ids, inactive_step_ids
from arctx.core.schema.payloads import UncutPayload


def uncut_impl(
    self,
    target_id: str,
    *,
    target_kind: Literal["node", "step"],
    reason: str | None = None,
    user_id: str | None = None,
    lane_id: str | None = None,
) -> UncutPayload:
    """Reverse a cut on a Node or Step by appending an UncutPayload."""
    if target_kind == "node":
        if target_id not in self.run_graph.nodes:
            raise KeyError(f"unknown node_id: {target_id}")
        if target_id not in cut_node_ids(self.run_graph):
            raise ValueError(f"node is not cut: {target_id}")
    elif target_kind == "step":
        if target_id not in self.run_graph.steps:
            raise KeyError(f"unknown step_id: {target_id}")
        if target_id not in cut_step_ids(self.run_graph):
            raise ValueError(f"step is not cut: {target_id}")
        # Reinstating a step must not give its output node a second active
        # producer (the "at most one active producer" invariant).
        output_node_id = self.run_graph.step_output(target_id)
        if output_node_id:
            inactive = inactive_step_ids(self.run_graph)
            for producer in self.run_graph.producers_of(output_node_id):
                if producer != target_id and producer not in inactive:
                    raise ValueError(
                        f"cannot uncut {target_id!r}: output node "
                        f"{output_node_id!r} already has an active producer "
                        f"{producer!r}; cut it first"
                    )
    else:
        raise ValueError(f"invalid target_kind: {target_kind!r}")

    uncut = UncutPayload(
        payload_id=self._next_id("pl"),
        target_id=target_id,
        target_kind=target_kind,
        reason=reason,
    )
    self.run_graph.attach_payload(uncut)
    self.record_work_event(
        user_id=user_id,
        lane_id=lane_id,
        event_type="uncut_added",
        target_kind=target_kind,
        target_id=target_id,
        created_records=(uncut.payload_id,),
        summary=reason,
    )
    return uncut
