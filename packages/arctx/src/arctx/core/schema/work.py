"""Append-only lane history records."""

from __future__ import annotations

from dataclasses import dataclass, field

from arctx.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class Lane:
    """A named, append-only unit of work within a run.

    A lane is NOT owned by one user — it may be SOLO (every event from one actor)
    or COLLABORATIVE (events from several). Membership is open: any actor may
    append to a shared lane. Per-action attribution lives on each
    :class:`WorkEvent`'s ``user_id``; ``created_by`` records who *opened*
    the lane. Lanes nest/branch via ``parent_lane_id``
    and are never deleted — closing is ``status``, rejection is a cut.
    """

    lane_id: str
    run_id: str
    created_by: str
    parent_lane_id: str | None = None
    started_at: str | None = None
    closed_at: str | None = None
    status: str = "open"
    metadata: dict[str, JSONValue] = field(default_factory=dict)
    name: str | None = None

    @property
    def user_id(self) -> str:
        """The actor who opened the lane. NOT an ownership lock."""
        return self.created_by

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]

@dataclass(frozen=True)
class WorkEvent:
    """A linear append-only event for a run's work history."""

    event_id: str
    run_id: str
    lane_id: str
    user_id: str
    event_type: str
    target_kind: str | None = None
    target_id: str | None = None
    created_records: tuple[str, ...] = ()
    summary: str | None = None
    data: dict[str, JSONValue] = field(default_factory=dict)
    created_at: str | None = None
    seq: int | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


def lane_from_dict(data: dict[str, JSONValue]) -> Lane:
    # Accept both the storage field names and the Lane aliases, so records
    # written either way (and older runs without ``name``) load unchanged.
    def pick(*keys):
        for k in keys:
            if data.get(k) is not None:
                return data[k]
        return None

    parent = pick("parent_lane_id", "parent_work_session_id")
    return Lane(
        lane_id=str(pick("lane_id", "work_session_id")),
        run_id=str(data["run_id"]),
        created_by=str(pick("created_by", "user_id")),
        parent_lane_id=str(parent) if parent is not None else None,
        started_at=str(data["started_at"]) if data.get("started_at") is not None else None,
        closed_at=str(data["closed_at"]) if data.get("closed_at") is not None else None,
        status=str(data.get("status") or "open"),
        metadata=dict(data.get("metadata") or {}),
        name=str(data["name"]) if data.get("name") is not None else None,
    )


def work_event_from_dict(data: dict[str, JSONValue]) -> WorkEvent:
    return WorkEvent(
        event_id=str(data["event_id"]),
        run_id=str(data["run_id"]),
        lane_id=str(data.get("lane_id") or data.get("work_session_id")),
        user_id=str(data["user_id"]),
        event_type=str(data["event_type"]),
        target_kind=str(data["target_kind"]) if data.get("target_kind") is not None else None,
        target_id=str(data["target_id"]) if data.get("target_id") is not None else None,
        created_records=tuple(str(v) for v in data.get("created_records") or ()),
        summary=str(data["summary"]) if data.get("summary") is not None else None,
        data=dict(data.get("data") or {}),
        created_at=str(data["created_at"]) if data.get("created_at") is not None else None,
        seq=int(data["seq"]) if data.get("seq") is not None else None,
    )
