"""RunHandle lane mutation helpers."""

from __future__ import annotations

from arctx.core.schema.work import WorkEvent
from arctx.core.types import JSONValue


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
        work_session_id=lane_id,
        event_type="lane_adopted",
        target_kind="subgraph",
        target_id=target_id or lane_id,
        created_records=(),
        summary=f"adopted {len(ids)} records",
        data=data,
    )
    if event is None:  # defensive; user_id/lane_id were validated above.
        raise RuntimeError("failed to record lane adoption event")
    return event
