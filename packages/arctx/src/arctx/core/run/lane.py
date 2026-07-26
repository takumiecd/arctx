"""RunHandle lane mutation helpers."""

from __future__ import annotations

from dataclasses import replace

from arctx.core.schema.work import WorkEvent
from arctx.core.types import JSONValue


def set_lane_status_impl(
    self,
    lane_id: str,
    *,
    status: str,
    user_id: str | None,
    reason: str | None = None,
) -> WorkEvent:
    """Open or close a lane by appending a status event (status is a projection).

    Records a ``lane_closed`` / ``lane_opened`` ``WorkEvent`` (the durable record)
    and folds it into the in-memory lane immediately so this session sees the new
    status. The lane record itself is never rewritten — it stays append-only.
    """
    if user_id is None:
        raise ValueError("user_id is required to change lane status")
    if status not in ("open", "closed"):
        raise ValueError(f"invalid lane status: {status!r} (expected 'open' or 'closed')")
    lane = self.run_graph.lanes.get(lane_id)
    if lane is None:
        raise KeyError(f"unknown lane: {lane_id}")

    event_type = "lane_closed" if status == "closed" else "lane_opened"
    data: dict[str, JSONValue] = {}
    if reason:
        data["reason"] = reason
    event = self.record_work_event(
        user_id=user_id,
        lane_id=lane_id,
        event_type=event_type,
        target_kind="lane",
        target_id=lane_id,
        summary=reason or f"lane {status}",
        data=data,
    )
    if event is None:  # defensive; user_id/lane_id validated above.
        raise RuntimeError("failed to record lane status event")

    if status == "closed":
        self.run_graph.lanes[lane_id] = replace(
            lane, status="closed", closed_at=event.created_at
        )
    else:
        self.run_graph.lanes[lane_id] = replace(lane, status="open", closed_at=None)
    return event
