"""Actor / Cursor schema for the multi-actor cursor model.

The data model deliberately separates two concerns:

- ``Actor`` is the principal that owns cursors. Humans, sub-agents,
  reviewers, executors all use the same shape; only ``actor_type``
  differs. ``Actor`` is frozen because identity should not drift in
  place — to mark someone as paused, append a new record (later, via
  an ActorStatusEvent) rather than mutate the existing one.

- ``Cursor`` is a mutable position pointer into the TraceDAG or
  PredictionDAG. Cursors are explicitly mutable: their ``current_state_id``
  moves as the actor advances, rewinds, or switches branches. The
  history of those moves can be recorded later via CursorEvent without
  changing the Cursor record itself.

This module only defines the records. Cursor manipulation APIs and
storage/CLI integration live elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from optagent.core.types import JSONValue, to_jsonable


DEFAULT_ACTOR_ID = "human"
DEFAULT_CURSOR_ID = "main"


ActorType = Literal["human", "agent"]
ActorStatus = Literal["active", "paused", "done", "abandoned"]
CursorStateKind = Literal["observed", "predicted"]
CursorStatus = Literal["active", "paused", "done", "abandoned"]


@dataclass(frozen=True)
class Actor:
    """A principal that can own cursors and produce records."""

    actor_id: str
    actor_type: ActorType
    name: str
    status: ActorStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass
class Cursor:
    """A mutable pointer to a State in the TraceDAG or PredictionDAG."""

    cursor_id: str
    owner_actor_id: str
    current_state_id: str
    state_kind: CursorStateKind
    name: str
    purpose: str | None = None
    status: CursorStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
