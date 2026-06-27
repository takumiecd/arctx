"""RunHandle lane mutation helpers."""

from __future__ import annotations

from dataclasses import replace

from arctx.core.lanes import ensure_valid_lanes
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


def adopt_lane_records_impl(
    self,
    lane_id: str,
    record_ids: list[str] | tuple[str, ...],
    *,
    user_id: str | None,
    mode: str = "explicit",
    target_id: str | None = None,
    reason: str | None = None,
) -> WorkEvent:
    """Adopt existing records into a lane without rewriting creation history."""
    if user_id is None:
        raise ValueError("user_id is required to adopt records into a lane")
    if lane_id not in self.run_graph.lanes:
        raise KeyError(f"unknown lane: {lane_id}")

    ids = tuple(dict.fromkeys(str(record_id) for record_id in record_ids))
    if not ids:
        raise ValueError("at least one record id is required")
    if self.root_node_id in ids:
        raise ValueError("run root cannot be adopted into a lane")

    known = set(self.run_graph.nodes) | set(self.run_graph.steps) | set(self.run_graph.payloads)
    unknown = [record_id for record_id in ids if record_id not in known]
    if unknown:
        raise KeyError(f"unknown record_id: {unknown[0]}")

    data: dict[str, JSONValue] = {
        "record_ids": list(ids),
        "mode": mode,
    }
    if reason:
        data["reason"] = reason

    event = self.record_work_event(
        user_id=user_id,
        lane_id=lane_id,
        event_type="lane_adopted",
        target_kind="subgraph",
        target_id=target_id or lane_id,
        created_records=(),
        summary=f"adopted {len(ids)} records",
        data=data,
    )
    if event is None:  # defensive; user_id/lane_id were validated above.
        raise RuntimeError("failed to record lane adoption event")
    try:
        ensure_valid_lanes(self.run_graph, root_node_id=self.root_node_id)
    except ValueError:
        if self.run_graph.work_events and self.run_graph.work_events[-1] == event:
            self.run_graph.work_events.pop()
        else:  # defensive: keep rollback correct if hooks append extra events later.
            self.run_graph.work_events = [
                existing
                for existing in self.run_graph.work_events
                if existing.event_id != event.event_id
            ]
        raise
    return event
