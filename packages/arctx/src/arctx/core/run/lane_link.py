"""RunHandle Lane DAG link implementation."""

from __future__ import annotations

from arctx.core.lanes import lane_descendants, lane_links


def link_lanes_impl(
    self,
    parent_lane_id: str,
    child_lane_id: str,
    *,
    user_id: str | None,
):
    """Append a parent-to-child Lane DAG edge, rejecting cycles."""
    if user_id is None:
        raise ValueError("user_id is required to link lanes")
    for lane_id in (parent_lane_id, child_lane_id):
        if lane_id not in self.run_graph.lanes:
            raise KeyError(f"unknown lane: {lane_id}")
    if parent_lane_id == child_lane_id:
        raise ValueError("lane DAG cannot contain a self-link")
    if parent_lane_id in lane_descendants(self.run_graph, child_lane_id):
        raise ValueError(
            f"lane link would create a cycle: {parent_lane_id} -> {child_lane_id}"
        )
    if any(
        link.parent_lane_id == parent_lane_id and link.child_lane_id == child_lane_id
        for link in lane_links(self.run_graph)
    ):
        raise ValueError(f"lane link already exists: {parent_lane_id} -> {child_lane_id}")
    event = self.record_work_event(
        user_id=user_id,
        lane_id=parent_lane_id,
        event_type="lane_linked",
        target_kind="lane",
        target_id=child_lane_id,
        summary=f"linked lane {child_lane_id}",
        data={
            "parent_lane_id": parent_lane_id,
            "child_lane_id": child_lane_id,
        },
    )
    if event is None:
        raise RuntimeError("failed to record lane link event")
    return event
