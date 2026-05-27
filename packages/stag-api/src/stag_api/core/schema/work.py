"""Append-only work history records."""

from __future__ import annotations

from dataclasses import dataclass, field

from stag_api.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class WorkSession:
    """A user-scoped unit of work within a run."""

    work_session_id: str
    run_id: str
    user_id: str
    parent_work_session_id: str | None = None
    started_at: str | None = None
    closed_at: str | None = None
    status: str = "open"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


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
    return WorkSession(
        work_session_id=str(data["work_session_id"]),
        run_id=str(data["run_id"]),
        user_id=str(data["user_id"]),
        parent_work_session_id=(
            str(data["parent_work_session_id"])
            if data.get("parent_work_session_id") is not None
            else None
        ),
        started_at=str(data["started_at"]) if data.get("started_at") is not None else None,
        closed_at=str(data["closed_at"]) if data.get("closed_at") is not None else None,
        status=str(data.get("status") or "open"),
        metadata=dict(data.get("metadata") or {}),
    )


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
