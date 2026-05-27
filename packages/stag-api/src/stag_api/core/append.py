"""Append-only storage batches for concurrent writers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from stag_api.core.graph_view import GraphView
from stag_api.core.schema.graph import Node, Transition
from stag_api.core.schema.payloads import PayloadBase
from stag_api.core.schema.work import WorkEvent, WorkSession

GraphRecordKind = Literal["node", "transition", "payload", "view"]
GraphRecord = Union[Node, Transition, PayloadBase, GraphView]


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
    work_session_id: str
    records: tuple[GraphRecordEnvelope, ...]
    work_session: WorkSession
    events: tuple[WorkEvent, ...]


@dataclass(frozen=True)
class AppendResult:
    """Result returned after an append batch is committed."""

    event_id: str
    event_seq: int
    record_ids: tuple[str, ...]
    event_ids: tuple[str, ...] = ()
    event_seqs: tuple[int, ...] = ()
