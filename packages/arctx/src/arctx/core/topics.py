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


def _forward_adjacency(graph: RunGraph) -> dict[str, list[str]]:
    """Directed adjacency over active records: input node → step → output."""
    inactive_n = inactive_node_ids(graph)
    inactive_s = inactive_step_ids(graph)
    adjacency: dict[str, list[str]] = {}
    for step in graph.steps.values():
        if step.step_id in inactive_s:
            continue
        for node_id in step.input_node_ids:
            if node_id not in inactive_n:
                adjacency.setdefault(node_id, []).append(step.step_id)
        if step.output_node_id not in inactive_n:
            adjacency.setdefault(step.step_id, []).append(step.output_node_id)
    return adjacency


def _descendants(adjacency: dict[str, list[str]], start: str) -> set[str]:
    seen: set[str] = set()
    queue = deque([start])
    while queue:
        for child in adjacency.get(queue.popleft(), ()):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return seen


def topic_islands(
    graph: RunGraph, records: list[TopicRecord]
) -> tuple[tuple[tuple[str, ...], ...], tuple[str, ...]]:
    """Group the active tagged records by *lineage*.

    Two tagged records belong to the same island when one derives from the
    other (directed reachability over the active graph), transitively through
    other tagged records. Sibling branches that merely share an ancestor are
    different islands — that is exactly the "same subject, independent
    lineages" signal the topic view exists to surface. Everything in a run
    hangs off the root, so undirected connectivity would collapse every topic
    into one island and say nothing.

    Returns ``(islands, inactive)``; cut records are reported separately
    rather than pretending they form islands of their own.
    """
    adjacency = _forward_adjacency(graph)
    active_ids = [r.record_id for r in records if r.active]
    inactive_ids = tuple(r.record_id for r in records if not r.active)
    descendants = {record_id: _descendants(adjacency, record_id) for record_id in active_ids}

    # Union tagged records related by ancestry (either direction).
    parent: dict[str, str] = {record_id: record_id for record_id in active_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(active_ids):
        for b in active_ids[i + 1 :]:
            if b in descendants[a] or a in descendants[b]:
                parent[find(a)] = find(b)

    groups: dict[str, list[str]] = {}
    for record_id in active_ids:
        groups.setdefault(find(record_id), []).append(record_id)
    islands = [tuple(members) for members in groups.values()]
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
