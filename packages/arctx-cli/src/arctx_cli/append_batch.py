"""Helpers for turning in-memory mutations into SQLite append batches."""

from __future__ import annotations

from arctx.core.append import AppendBatch, GraphRecordEnvelope


def graph_counts(handle) -> dict[str, set[str]]:
    """Capture graph record IDs before a mutation."""
    return {
        "nodes": set(handle.run_graph.nodes),
        "transitions": set(handle.run_graph.transitions),
        "payloads": set(handle.run_graph.payloads),
        "work_events": {event.event_id for event in handle.run_graph.work_events},
    }


def maybe_append_or_save(
    *,
    store,
    handle,
    user_id: str | None,
    work_session_id: str | None,
    before: dict[str, set[str]],
) -> None:
    """Use append_batch for capable stores, otherwise fall back to save_run."""
    if user_id is None or work_session_id is None or not hasattr(store, "append_batch"):
        store.save_run(handle)
        return
    store.append_batch(
        build_append_batch(
            handle,
            user_id=user_id,
            work_session_id=work_session_id,
            before=before,
        )
    )


def build_append_batch(
    handle,
    *,
    user_id: str,
    work_session_id: str,
    before: dict[str, set[str]],
) -> AppendBatch:
    """Build an append batch from records added since *before*."""
    records: list[GraphRecordEnvelope] = []

    for node_id in _new_ids(handle.run_graph.nodes, before, "nodes"):
        node = handle.run_graph.nodes[node_id]
        records.append(GraphRecordEnvelope("node", node.node_id, node))

    for transition_id in _new_ids(handle.run_graph.transitions, before, "transitions"):
        transition = handle.run_graph.transitions[transition_id]
        records.append(GraphRecordEnvelope("transition", transition.transition_id, transition))

    for payload_id in _new_ids(handle.run_graph.payloads, before, "payloads"):
        payload = handle.run_graph.payloads[payload_id]
        records.append(GraphRecordEnvelope("payload", payload.payload_id, payload))

    new_events = [
        event
        for event in handle.run_graph.work_events
        if event.event_id not in before.get("work_events", set())
    ]
    if not new_events:
        raise RuntimeError("append batch requires at least one work event")

    session = handle.run_graph.work_sessions[work_session_id]
    return AppendBatch(
        run_id=handle.run_id,
        user_id=user_id,
        work_session_id=work_session_id,
        work_session=session,
        events=tuple(new_events),
        records=tuple(records),
    )


def _new_ids(current: dict[str, object], before: dict[str, set[str]], key: str) -> list[str]:
    return [record_id for record_id in current if record_id not in before.get(key, set())]
