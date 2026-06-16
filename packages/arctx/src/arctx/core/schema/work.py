"""Append-only work history records."""

from __future__ import annotations

from dataclasses import dataclass, field

from arctx.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class WorkSession:
    """A **Lane**: a named, append-only unit of work within a run.

    A lane is NOT owned by one user — it may be SOLO (every event from one actor)
    or COLLABORATIVE (events from several). Membership is open: any actor may
    append to a shared lane. Per-action attribution lives on each
    :class:`WorkEvent`'s ``user_id``; ``user_id`` here only records who *opened*
    the lane (``created_by``). Lanes nest/branch via ``parent_work_session_id``
    and are never deleted — closing is ``status``, rejection is a cut.

    ``Lane`` is the canonical public name; the field names keep the
    ``work_session`` spelling for storage/back-compat (``lane_id`` /
    ``created_by`` / ``parent_lane_id`` are read-only aliases). A full field
    rename + storage migration is a separate follow-up.
    """

    work_session_id: str
    run_id: str
    user_id: str
    parent_work_session_id: str | None = None
    started_at: str | None = None
    closed_at: str | None = None
    status: str = "open"
    metadata: dict[str, JSONValue] = field(default_factory=dict)
    name: str | None = None

    # -- Lane aliases (read-only views over the back-compat field names) --------
    @property
    def lane_id(self) -> str:
        return self.work_session_id

    @property
    def created_by(self) -> str:
        """The actor who opened the lane. NOT an ownership lock."""
        return self.user_id

    @property
    def parent_lane_id(self) -> str | None:
        return self.parent_work_session_id

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


#: Canonical public name for the work-unit concept (solo-or-collaborative).
Lane = WorkSession


@dataclass(frozen=True)
class WorkEvent:
    """A linear append-only event for a run's work history."""

    event_id: str
    run_id: str
    work_session_id: str
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


def work_session_from_dict(data: dict[str, JSONValue]) -> WorkSession:
    # Accept both the storage field names and the Lane aliases, so records
    # written either way (and older runs without ``name``) load unchanged.
    def pick(*keys):
        for k in keys:
            if data.get(k) is not None:
                return data[k]
        return None

    parent = pick("parent_work_session_id", "parent_lane_id")
    return WorkSession(
        work_session_id=str(pick("work_session_id", "lane_id")),
        run_id=str(data["run_id"]),
        user_id=str(pick("user_id", "created_by")),
        parent_work_session_id=str(parent) if parent is not None else None,
        started_at=str(data["started_at"]) if data.get("started_at") is not None else None,
        closed_at=str(data["closed_at"]) if data.get("closed_at") is not None else None,
        status=str(data.get("status") or "open"),
        metadata=dict(data.get("metadata") or {}),
        name=str(data["name"]) if data.get("name") is not None else None,
    )


#: Alias: lanes deserialize through the same back-compat reader.
lane_from_dict = work_session_from_dict


def work_event_from_dict(data: dict[str, JSONValue]) -> WorkEvent:
    return WorkEvent(
        event_id=str(data["event_id"]),
        run_id=str(data["run_id"]),
        work_session_id=str(data["work_session_id"]),
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
