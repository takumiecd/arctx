"""RunHandle.cut implementation."""

from __future__ import annotations

from typing import Literal

from arctx.core.cuts import cut_node_ids, cut_step_ids
from arctx.core.schema.payloads import CutPayload


def cut_impl(
    self,
    target_id: str,
    *,
    target_kind: Literal["node", "step"],
    reason: str | None = None,
    user_id: str | None = None,
    lane_id: str | None = None,
) -> CutPayload:
    """Append a CutPayload to mark a Node or Step inactive."""
    if target_kind == "node":
        if target_id not in self.run_graph.nodes:
            raise KeyError(f"unknown node_id: {target_id}")
        if target_id in cut_node_ids(self.run_graph):
            raise ValueError(f"node already cut: {target_id}")
    elif target_kind == "step":
        if target_id not in self.run_graph.steps:
            raise KeyError(f"unknown step_id: {target_id}")
        if target_id in cut_step_ids(self.run_graph):
            raise ValueError(f"step already cut: {target_id}")
    else:
        raise ValueError(f"invalid target_kind: {target_kind!r}")

    cut = CutPayload(
        payload_id=self._next_id("pl"),
        target_id=target_id,
        target_kind=target_kind,
        reason=reason,
    )
    self.run_graph.attach_payload(cut)
    self.record_work_event(
        user_id=user_id,
        lane_id=lane_id,
        event_type="cut_added",
        target_kind=target_kind,
        target_id=target_id,
        created_records=(cut.payload_id,),
        summary=reason,
    )
    return cut
