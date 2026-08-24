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
    # False when the writer asked to respect the lane's closed state, so the
    # store can re-check it under the lock. The CLI's gate runs before the lock,
    # against the writer's own snapshot, so a lane closed in between slipped
    # through. True means the writer passed --force and meant it.
    force: bool = False


def apply_to_graph(graph, batch: "AppendBatch") -> None:
    """Add *batch*'s records to *graph* in place, skipping ids it already has.

    Used to ask "what would this batch make the run look like?" against a graph
    freshly read from disk, so a writer's decision can be checked against the
    state it will actually land in rather than the snapshot it was made on.
    """
    if batch.lane.lane_id not in graph.lanes:
        graph.add_lane(batch.lane)
    for envelope in batch.records:
        if envelope.record_kind == "node":
            if envelope.record_id not in graph.nodes:
                graph.nodes[envelope.record_id] = envelope.record
        elif envelope.record_kind == "step":
            if envelope.record_id not in graph.steps:
                graph.add_step(envelope.record)
        elif envelope.record_id not in graph.payloads:
            graph.attach_payload(envelope.record)
    known = {event.event_id for event in graph.work_events}
    for event in batch.events:
        if event.event_id not in known:
            graph.add_work_event(event)


@dataclass(frozen=True)
class AppendResult:
    """Result returned after an append batch is committed."""

    event_id: str
    event_seq: int
    record_ids: tuple[str, ...]
    event_ids: tuple[str, ...] = ()
    event_seqs: tuple[int, ...] = ()
