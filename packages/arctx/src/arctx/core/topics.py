"""Derived topics — flat, name-keyed bundles of meaning across the graph.

A topic is the third flat-name bundle, next to lanes (bundles of work) and
trial tables (bundles of numbers): any node or step can carry a topic name,
and everything a reader looks at is derived from the payloads that carry the
name. No topic record exists.

Two payload flavors carry a topic, both plain generic payloads (no new
payload class — old readers degrade gracefully):

- ``type="tag"``, ``content={"topic": NAME, "note": ...}`` — a membership
  mark attached to the tagged record itself. Tagging never requires the
  tagged records to be connected: discovering that records in *different*
  regions share a topic is the point, not a violation.
- ``type="topic_summary"``, ``content={"topic": NAME, "text": ..., "sources":
  [ids]}`` — the current statement about the topic ("a strong tag"). Attached
  to the node where it was written (provenance). The effective statement is
  the latest one by record_event_rank — same supersession as lane summaries.

The derived view groups a topic's tagged records into *islands*: connected
components over the active graph. Two or more islands is a signal, not an
error — it says "these regions are about the same thing but not yet joined";
joining them stays a human/agent decision (``arctx add --from A --from B``).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from arctx.core.cuts import inactive_node_ids, inactive_step_ids
from arctx.core.lanes import record_event_rank
from arctx.core.run_graph import RunGraph
from arctx.core.schema.payloads import PayloadBase

TAG_TYPE = "tag"
SUMMARY_TYPE = "topic_summary"


def _payload_topic(payload: PayloadBase) -> str | None:
    if getattr(payload, "type", None) not in (TAG_TYPE, SUMMARY_TYPE):
        return None
    content = getattr(payload, "content", None) or {}
    topic = content.get("topic")
    return topic if isinstance(topic, str) and topic.strip() else None


@dataclass(frozen=True)
class TopicRecord:
    record_id: str
    kind: str  # "node" | "step"
    active: bool
    note: str | None
    payload_id: str  # the tag payload


@dataclass(frozen=True)
class TopicSummary:
    payload_id: str
    target_id: str
    text: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class TopicView:
    name: str
    summary: TopicSummary | None
    islands: tuple[tuple[str, ...], ...]  # active record ids, grouped
    inactive: tuple[str, ...]  # cut tagged records, kept visible
    records: tuple[TopicRecord, ...]


def topic_names(graph: RunGraph) -> list[str]:
    """Topic names in first-appearance order (tags and summaries alike)."""
    seen: list[str] = []
    for payload in graph.payloads.values():
        topic = _payload_topic(payload)
        if topic is not None and topic not in seen:
            seen.append(topic)
    return seen


def _tag_records(graph: RunGraph, name: str) -> list[TopicRecord]:
    inactive_n = inactive_node_ids(graph)
    inactive_s = inactive_step_ids(graph)
    records: list[TopicRecord] = []
    seen: set[str] = set()
    for payload in graph.payloads.values():
        if getattr(payload, "type", None) != TAG_TYPE:
            continue
        if _payload_topic(payload) != name:
            continue
        record_id = payload.target_id
        if record_id in seen:
            continue
        seen.add(record_id)
        kind = "node" if record_id in graph.nodes else "step"
        active = (
            record_id not in inactive_n
            if kind == "node"
            else record_id not in inactive_s
        )
        note = (getattr(payload, "content", None) or {}).get("note")
        records.append(
            TopicRecord(
                record_id=record_id,
                kind=kind,
                active=active,
                note=note if isinstance(note, str) else None,
                payload_id=payload.payload_id,
            )
        )
    return records


def topic_current_summary(graph: RunGraph, name: str) -> TopicSummary | None:
    """The latest topic_summary payload for *name*, by record_event_rank."""
    rank = record_event_rank(graph)
    best: tuple[int, PayloadBase] | None = None
    for payload in graph.payloads.values():
        if getattr(payload, "type", None) != SUMMARY_TYPE:
            continue
        if _payload_topic(payload) != name:
            continue
        payload_rank = rank.get(payload.payload_id, -1)
        # >= so equal ranks fall back to append order: payloads written
        # without a lane/user carry no work event and all rank -1.
        if best is None or payload_rank >= best[0]:
            best = (payload_rank, payload)
    if best is None:
        return None
    content = getattr(best[1], "content", None) or {}
    sources = content.get("sources") or ()
    return TopicSummary(
        payload_id=best[1].payload_id,
        target_id=best[1].target_id,
        text=str(content.get("text", "")),
        sources=tuple(str(s) for s in sources),
    )


def _active_adjacency(graph: RunGraph) -> dict[str, list[str]]:
    """Undirected adjacency over active nodes and steps.

    A step links each of its input nodes and its output node; direction is
    irrelevant for "are these regions part of one body of work".
    """
    inactive_n = inactive_node_ids(graph)
    inactive_s = inactive_step_ids(graph)
    adjacency: dict[str, list[str]] = {}

    def link(a: str, b: str) -> None:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    for step in graph.steps.values():
        if step.step_id in inactive_s:
            continue
        for node_id in (*step.input_node_ids, step.output_node_id):
            if node_id not in inactive_n:
                link(step.step_id, node_id)
    return adjacency


def topic_islands(
    graph: RunGraph, records: list[TopicRecord]
) -> tuple[tuple[tuple[str, ...], ...], tuple[str, ...]]:
    """Group the active tagged records by graph connectivity.

    Returns ``(islands, inactive)``: islands are tuples of tagged record ids
    that reach each other through the active graph; cut records are reported
    separately rather than pretending they form islands of their own.
    """
    adjacency = _active_adjacency(graph)
    active_ids = [r.record_id for r in records if r.active]
    inactive_ids = tuple(r.record_id for r in records if not r.active)
    unassigned = set(active_ids)
    islands: list[tuple[str, ...]] = []
    while unassigned:
        seed = next(iter(unassigned))
        component: set[str] = set()
        queue = deque([seed])
        visited: set[str] = {seed}
        while queue:
            current = queue.popleft()
            if current in unassigned:
                component.add(current)
            for neighbor in adjacency.get(current, ()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        unassigned -= component
        islands.append(tuple(sorted(component, key=active_ids.index)))
    islands.sort(key=lambda island: active_ids.index(island[0]))
    return tuple(islands), inactive_ids


def topic_view(graph: RunGraph, name: str) -> TopicView:
    records = _tag_records(graph, name)
    islands, inactive = topic_islands(graph, records)
    return TopicView(
        name=name,
        summary=topic_current_summary(graph, name),
        islands=islands,
        inactive=inactive,
        records=tuple(records),
    )


def list_topics(graph: RunGraph) -> list[TopicView]:
    return [topic_view(graph, name) for name in topic_names(graph)]


__all__ = [
    "SUMMARY_TYPE",
    "TAG_TYPE",
    "TopicRecord",
    "TopicSummary",
    "TopicView",
    "list_topics",
    "topic_current_summary",
    "topic_islands",
    "topic_names",
    "topic_view",
]
