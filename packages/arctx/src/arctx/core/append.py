"""Append-only storage batches for concurrent writers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from arctx.core.schema.graph import Node, Step
from arctx.core.schema.payloads import PayloadBase
from arctx.core.schema.work import WorkEvent, Lane

GraphRecordKind = Literal["node", "step", "payload"]
GraphRecord = Union[Node, Step, PayloadBase]


@dataclass(frozen=True)
class GraphRecordEnvelope:
    """A graph record plus the table/category it belongs to."""

    record_kind: GraphRecordKind
    record_id: str
    record: GraphRecord


@dataclass(frozen=True)
class AppendBatch:
    """One atomic append unit for a run."""

    run_id: str
    user_id: str
    lane_id: str
    records: tuple[GraphRecordEnvelope, ...]
    lane: Lane
    events: tuple[WorkEvent, ...]


@dataclass(frozen=True)
class AppendResult:
    """Result returned after an append batch is committed."""

    event_id: str
    event_seq: int
    record_ids: tuple[str, ...]
    event_ids: tuple[str, ...] = ()
    event_seqs: tuple[int, ...] = ()
