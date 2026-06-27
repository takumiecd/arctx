"""Pure request dispatcher for the local ARCTX run API."""

from __future__ import annotations

import re
from typing import Any

from arctx.core.append import AppendBatch, GraphRecordEnvelope
from arctx.core.lanes import format_lane_validation_errors, lane_membership, lane_validation_errors
from arctx.core.run.export import ExportOptions, json_document
from arctx.payload_builder import build_payload


class ApiError(Exception):
    """Raised inside a handler to return a non-2xx JSON error."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def dispatch(
    store: Any,
    run_id: str,
    method: str,
    path: str,
    body: dict | None,
    *,
    user_id: str,
    lane_id: str,
    query: dict | None = None,
) -> tuple[int, dict]:
    route = (method.upper(), path.rstrip("/") or "/")
    try:
        if route == ("GET", "/health"):
            return 200, {"status": "ok", "run_id": run_id}
        if route == ("GET", "/runs"):
            return 200, {"runs": store.list_runs(), "current_run_id": run_id}
        if route == ("POST", "/runs"):
            return 201, _post_runs(store, body or {})
        if route == ("GET", "/run"):
            return 200, _get_run(store, run_id, lane_id)
        if route == ("GET", "/assets/visible"):
            return 200, _get_visible_assets(store, run_id, query or {})
        if route == ("POST", "/step"):
            return 201, _post_step(store, run_id, body or {}, user_id, lane_id)
        if route == ("POST", "/attach"):
            return 201, _post_attach(store, run_id, body or {}, user_id, lane_id)
        if route == ("POST", "/cut"):
            return 201, _post_cut(store, run_id, body or {}, user_id, lane_id)
        if route == ("POST", "/uncut"):
            return 201, _post_uncut(store, run_id, body or {}, user_id, lane_id)
        if route == ("POST", "/reparent"):
            return 201, _post_reparent(store, run_id, body or {}, user_id, lane_id)
        if route == ("POST", "/lane"):
            return 201, _post_lane(store, run_id, body or {}, user_id)
        if route == ("POST", "/lane/adopt"):
            return 201, _post_lane_adopt(store, run_id, body or {}, user_id)
        if route == ("GET", "/ext"):
            return 200, _get_ext(store, run_id)
        if route == ("POST", "/ext/enable"):
            return 200, _post_ext_enable(store, run_id, body or {})
        if route == ("POST", "/ext/disable"):
            return 200, _post_ext_disable(store, run_id, body or {})
        if route == ("POST", "/artifacts/upload"):
            return 201, _post_artifacts_upload(store, run_id, body or {})
        return 404, {"error": f"no route for {method} {path}"}
    except ApiError as exc:
        return exc.status, {"error": exc.message}
    except (KeyError, ValueError, TypeError) as exc:
        return 400, {"error": str(exc)}


def _load(store: Any, run_id: str):
    if not store.run_path(run_id).exists():
        raise ApiError(404, f"unknown run_id: {run_id}")
    return store.load_run(run_id)


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _post_runs(store: Any, body: dict) -> dict:
    import arctx as arctx
    from arctx.core.schema.requirements import Requirement

    raw_id = body.get("run_id") or body.get("name")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise ApiError(400, "run_id (or name) is required")
    run_id = raw_id.strip()
    if run_id in (".", "..") or not _RUN_ID_RE.match(run_id):
        raise ApiError(400, "run_id may contain only letters, digits, '.', '_' and '-'")
    if store.run_path(run_id).exists():
        raise ApiError(400, f"run already exists: {run_id!r}")

    requirement_id = str(body.get("requirement_id") or run_id)
    target_type = str(body.get("target_type") or "code")
    target_id = str(body.get("target_id") or requirement_id)

    handle = arctx.init(
        Requirement(
            requirement_id=requirement_id,
            target_type=target_type,
            target_id=target_id,
        ),
        run_id=run_id,
    )
    store.save_run(handle)
    return {
        "run": {
            "run_id": handle.run_id,
            "requirement_id": requirement_id,
            "target_type": target_type,
            "target_id": target_id,
        },
        "run_id": handle.run_id,
        "root_node_id": handle.root_node_id,
    }


def _get_run(store: Any, run_id: str, lane_id: str) -> dict:
    handle = _load(store, run_id)
    doc = json_document(handle, ExportOptions())
    lane = handle.run_graph.lanes.get(lane_id)
    doc["current_lane_id"] = lane_id
    doc["current_lane_name"] = lane.name if lane is not None else lane_id
    return doc


def _get_visible_assets(store: Any, run_id: str, query: dict) -> dict:
    from arctx.core.lineage import is_visible_from

    from_id = query.get("from")
    if not from_id:
        raise ApiError(400, "query parameter 'from' is required")
    from_id = str(from_id)

    handle = _load(store, run_id)
    graph = handle.run_graph
    if from_id in graph.nodes:
        viewer = ("node", from_id)
    elif from_id in graph.steps:
        viewer = ("step", from_id)
    else:
        raise ApiError(404, f"unknown record: {from_id}")

    assets: list[dict] = []
    for payload in graph.payloads.values():
        if getattr(payload, "payload_type", None) != "asset":
            continue
        target_kind = getattr(payload, "target_kind", None)
        target_id = getattr(payload, "target_id", None)
        if target_kind not in ("node", "step") or not target_id:
            continue
        try:
            if is_visible_from(graph, (target_kind, target_id), viewer):
                assets.append(payload.to_dict())
        except KeyError:
            continue
    return {"from": from_id, "assets": assets}


def _payload_fields(body: dict) -> dict:
    exclude = {
        "payload_type", "target_id", "target_kind", "node_id",
        "input_node_ids", "output_node_id", "reason",
    }
    return {k: v for k, v in body.items() if k not in exclude}


def _post_step(store, run_id, body, user_id, lane_id) -> dict:
    inputs = body.get("input_node_ids")
    if not isinstance(inputs, list) or not inputs:
        raise ApiError(400, "input_node_ids must be a non-empty list")
    output_node_id = body.get("output_node_id")

    handle = _load(store, run_id)
    baseline = _lane_error_baseline(handle)
    payload = build_payload(
        payload_type=str(body.get("payload_type", "step_payload")),
        target_kind="step",
        target_id="pending",
        payload_id="pending",
        json_data=_payload_fields(body),
    )
    before = _graph_counts(handle)
    step = handle.add_step(
        [str(n) for n in inputs],
        payload,
        output_node_id=str(output_node_id) if output_node_id else None,
        user_id=user_id,
        lane_id=lane_id,
    )
    _ensure_lane_integrity(handle, baseline=baseline)
    _maybe_append_or_save(store=store, handle=handle, user_id=user_id, lane_id=lane_id, before=before)
    return {"step": _step_view(step)}


def _post_attach(store, run_id, body, user_id, lane_id) -> dict:
    target_id = body.get("target_id") or body.get("node_id")
    if not target_id:
        raise ApiError(400, "target_id is required")
    target_id = str(target_id)

    handle = _load(store, run_id)
    target_kind = body.get("target_kind")
    if target_kind not in ("node", "step"):
        target_kind = _resolve_target_kind(handle, target_id)
    if target_kind not in ("node", "step"):
        raise ApiError(400, "target must be a node or a step")

    default_type = "node_payload" if target_kind == "node" else "step_payload"
    payload = build_payload(
        payload_type=str(body.get("payload_type", default_type)),
        target_kind=target_kind,
        target_id=target_id,
        payload_id=handle._next_id("pl"),
        json_data=_payload_fields(body),
    )

    before = _graph_counts(handle)
    if target_kind == "node":
        attached = handle.attach(target_id, payload, user_id=user_id, lane_id=lane_id)
    else:
        if target_id not in handle.run_graph.steps:
            raise ApiError(404, f"unknown step_id: {target_id}")
        handle.run_graph.attach_payload(payload)
        handle.record_work_event(
            user_id=user_id,
            lane_id=lane_id,
            event_type="payload_attached",
            target_kind="step",
            target_id=target_id,
            created_records=(payload.payload_id,),
            summary=payload.payload_type,
        )
        attached = payload

    _maybe_append_or_save(store=store, handle=handle, user_id=user_id, lane_id=lane_id, before=before)
    return {"payload": attached.to_dict()}


def _post_cut(store, run_id, body, user_id, lane_id) -> dict:
    target_id = body.get("target_id")
    target_kind = body.get("target_kind")
    if not target_id:
        raise ApiError(400, "target_id is required")
    if target_kind not in ("node", "step"):
        raise ApiError(400, "target_kind must be 'node' or 'step'")

    handle = _load(store, run_id)
    before = _graph_counts(handle)
    cut = handle.cut(str(target_id), target_kind=target_kind, reason=body.get("reason"), user_id=user_id, lane_id=lane_id)
    _maybe_append_or_save(store=store, handle=handle, user_id=user_id, lane_id=lane_id, before=before)
    return {"payload": cut.to_dict()}


def _post_uncut(store, run_id, body, user_id, lane_id) -> dict:
    target_id = body.get("target_id")
    target_kind = body.get("target_kind")
    if not target_id:
        raise ApiError(400, "target_id is required")
    if target_kind not in ("node", "step"):
        raise ApiError(400, "target_kind must be 'node' or 'step'")

    handle = _load(store, run_id)
    before = _graph_counts(handle)
    uncut = handle.uncut(str(target_id), target_kind=target_kind, reason=body.get("reason"), user_id=user_id, lane_id=lane_id)
    _maybe_append_or_save(store=store, handle=handle, user_id=user_id, lane_id=lane_id, before=before)
    return {"payload": uncut.to_dict()}


def _post_reparent(store, run_id, body, user_id, lane_id) -> dict:
    node_id = body.get("node_id") or body.get("target_id")
    if not node_id:
        raise ApiError(400, "node_id is required")
    inputs = body.get("input_node_ids")
    if not isinstance(inputs, list) or not inputs:
        raise ApiError(400, "input_node_ids must be a non-empty list")

    handle = _load(store, run_id)
    baseline = _lane_error_baseline(handle)
    payload = build_payload(
        payload_type=str(body.get("payload_type", "step_payload")),
        target_kind="step",
        target_id="pending",
        payload_id="pending",
        json_data=_payload_fields(body),
    )
    before = _graph_counts(handle)
    step = handle.reparent(
        str(node_id),
        [str(n) for n in inputs],
        payload,
        reason=body.get("reason"),
        user_id=user_id,
        lane_id=lane_id,
    )
    _ensure_lane_integrity(handle, baseline=baseline)
    _maybe_append_or_save(store=store, handle=handle, user_id=user_id, lane_id=lane_id, before=before)
    return {"step": _step_view(step)}


def _post_lane(store, run_id, body, user_id) -> dict:
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ApiError(400, "name is required")
    metadata = body.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ApiError(400, "metadata must be an object")

    handle = _load(store, run_id)
    if any(lane.name == name.strip() for lane in handle.run_graph.lanes.values()):
        raise ApiError(400, f"lane already exists: {name.strip()!r}")
    lane = handle.ensure_lane(name=name.strip(), created_by=user_id, metadata=metadata)
    store.save_run(handle)
    return {"lane": lane.to_dict()}


def _post_lane_adopt(store, run_id, body, user_id) -> dict:
    lane_ref = body.get("lane_id") or body.get("name")
    if not isinstance(lane_ref, str) or not lane_ref.strip():
        raise ApiError(400, "lane_id or name is required")

    handle = _load(store, run_id)
    lane = handle.run_graph.lanes.get(lane_ref)
    if lane is None:
        lane = next((candidate for candidate in handle.run_graph.lanes.values() if candidate.name == lane_ref), None)
    if lane is None:
        raise ApiError(404, f"unknown lane: {lane_ref}")

    ids, mode, target_id = _adoption_record_ids(handle, body)
    before = _graph_counts(handle)
    event = handle.adopt_lane_records(
        lane.lane_id,
        ids,
        user_id=user_id,
        mode=mode,
        target_id=target_id,
        reason=body.get("reason") if isinstance(body.get("reason"), str) else None,
    )
    _maybe_append_or_save(store=store, handle=handle, user_id=user_id, lane_id=lane.lane_id, before=before)
    return {
        "lane_id": lane.lane_id,
        "name": lane.name,
        "adopted_record_ids": list(ids),
        "count": len(ids),
        "mode": mode,
        "event_id": event.event_id,
    }


def _adoption_record_ids(handle, body: dict) -> tuple[tuple[str, ...], str, str]:
    record_ids = body.get("record_ids")
    history_node_id = body.get("history_node_id")
    reachable_node_id = body.get("reachable_node_id")
    lane_head_node_id = body.get("lane_head_node_id")
    lane_tail_node_id = body.get("lane_tail_node_id")
    sources = [
        isinstance(record_ids, list) and bool(record_ids),
        history_node_id is not None,
        reachable_node_id is not None,
        lane_head_node_id is not None,
        lane_tail_node_id is not None,
    ]
    if sum(1 for enabled in sources if enabled) != 1:
        raise ApiError(400, "choose exactly one of record_ids, history_node_id, reachable_node_id, lane_head_node_id, lane_tail_node_id")

    if isinstance(record_ids, list) and record_ids:
        ids = tuple(dict.fromkeys(str(record_id) for record_id in record_ids))
        return ids, "explicit", ids[0]

    if history_node_id is not None:
        node_id = str(history_node_id)
        if node_id not in handle.run_graph.nodes:
            raise ApiError(404, f"unknown node_id: {node_id}")
        trace = handle.trace(node_id)
        ids = trace.past_node_ids + (trace.current_node_id,) + trace.step_ids + trace.payload_ids
        return _without_run_root(handle, ids), "history", node_id

    if lane_head_node_id is not None:
        node_id = str(lane_head_node_id)
        ids = _lane_local_head_record_ids(handle, node_id)
        return _without_run_root(handle, ids), "lane_head", node_id

    if lane_tail_node_id is not None:
        node_id = str(lane_tail_node_id)
        ids = _lane_local_tail_record_ids(handle, node_id)
        return _without_run_root(handle, ids), "lane_tail", node_id

    node_id = str(reachable_node_id)
    if node_id not in handle.run_graph.nodes:
        raise ApiError(404, f"unknown node_id: {node_id}")
    reachable = handle.run_graph.reachable_from(node_id)
    producer_step_id = handle.run_graph.step_to_node(node_id)
    producer_step_ids = (producer_step_id,) if producer_step_id is not None else ()
    ids = (
        (node_id,)
        + tuple(reachable["node_ids"])
        + producer_step_ids
        + tuple(reachable["step_ids"])
        + tuple(reachable["payload_ids"])
    )
    return _without_run_root(handle, ids), "reachable", node_id


def _lane_local_head_record_ids(handle, node_id: str) -> tuple[str, ...]:
    if node_id not in handle.run_graph.nodes:
        raise ApiError(404, f"unknown node_id: {node_id}")
    membership = lane_membership(handle.run_graph)
    lane_id = membership.node_to_lane.get(node_id)
    if lane_id is None:
        raise ApiError(400, f"node {node_id} is not lane-owned")
    ids: list[str] = [node_id]
    current = node_id
    while True:
        step_id = handle.run_graph.step_to_node(current)
        if step_id is None:
            break
        if membership.step_to_lane.get(step_id) != lane_id:
            break
        ids.append(step_id)
        step = handle.run_graph.steps[step_id]
        if not step.input_node_ids:
            break
        parent = step.input_node_ids[0]
        if membership.node_to_lane.get(parent) != lane_id:
            break
        ids.append(parent)
        current = parent
    return tuple(dict.fromkeys(ids))


def _lane_local_tail_record_ids(handle, node_id: str) -> tuple[str, ...]:
    if node_id not in handle.run_graph.nodes:
        raise ApiError(404, f"unknown node_id: {node_id}")
    membership = lane_membership(handle.run_graph)
    lane_id = membership.node_to_lane.get(node_id)
    if lane_id is None:
        raise ApiError(400, f"node {node_id} is not lane-owned")
    ids: list[str] = [node_id]
    producer_step_id = handle.run_graph.step_to_node(node_id)
    if producer_step_id is not None and membership.step_to_lane.get(producer_step_id) == lane_id:
        ids.append(producer_step_id)
    frontier = [node_id]
    seen_nodes = {node_id}
    while frontier:
        current = frontier.pop()
        for step_id in handle.run_graph.steps_from_node(current):
            if membership.step_to_lane.get(step_id) != lane_id:
                continue
            ids.append(step_id)
            child = handle.run_graph.steps[step_id].output_node_id
            if child in seen_nodes or membership.node_to_lane.get(child) != lane_id:
                continue
            seen_nodes.add(child)
            ids.append(child)
            frontier.append(child)
    return tuple(dict.fromkeys(ids))


def _without_run_root(handle, ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(record_id for record_id in ids if record_id != handle.root_node_id)


def _lane_error_baseline(handle) -> int:
    return len(lane_validation_errors(handle.run_graph))


def _ensure_lane_integrity(handle, *, baseline: int) -> None:
    errors = lane_validation_errors(handle.run_graph)
    if len(errors) > baseline:
        raise ApiError(400, format_lane_validation_errors(errors[baseline:]))


def _get_ext(store, run_id: str) -> dict:
    from arctx.ext import list_available
    from arctx.ext.enabled import load_enabled

    enabled = {item.name for item in load_enabled(store.run_path(run_id))}
    extensions = [
        {"name": name, "enabled": name in enabled}
        for name in list_available()
    ]
    return {
        "extensions": extensions,
        "available": [item["name"] for item in extensions],
        "enabled": sorted(enabled),
    }


def _post_ext_enable(store, run_id: str, body: dict) -> dict:
    from arctx.ext import load_extension
    from arctx.ext.enabled import EnabledExtension, add_enabled, load_enabled

    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ApiError(400, "name is required")
    ext = load_extension(name.strip())
    before = {item.name for item in load_enabled(store.run_path(run_id))}
    add_enabled(store.run_path(run_id), EnabledExtension(name=ext.name, version=ext.version))
    status = "already_enabled" if ext.name in before else "enabled"
    return {"status": status, "name": ext.name, "version": ext.version}


def _post_ext_disable(store, run_id: str, body: dict) -> dict:
    from arctx.ext.enabled import load_enabled, save_enabled

    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ApiError(400, "name is required")
    ext_name = name.strip()
    current = load_enabled(store.run_path(run_id))
    kept = [item for item in current if item.name != ext_name]
    save_enabled(store.run_path(run_id), kept)
    return {"status": "disabled", "name": ext_name}


def _post_artifacts_upload(store, run_id: str, body: dict) -> dict:
    import base64
    import uuid
    from pathlib import Path

    filename = body.get("filename")
    file_data = body.get("file_data")
    if not isinstance(filename, str) or not filename:
        raise ApiError(400, "filename is required")
    if not isinstance(file_data, str) or not file_data:
        raise ApiError(400, "file_data is required")

    safe_name = Path(filename).name
    if safe_name in ("", ".", ".."):
        raise ApiError(400, "filename must be a plain file name")
    try:
        raw = base64.b64decode(file_data, validate=True)
    except ValueError as exc:
        raise ApiError(400, f"invalid base64 file_data: {exc}") from exc

    if not store.run_path(run_id).exists():
        raise ApiError(404, f"unknown run_id: {run_id}")

    stem = f"art_{uuid.uuid4().hex[:8]}_{safe_name}"
    artifacts_dir = store.run_path(run_id) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    target = artifacts_dir / stem
    target.write_bytes(raw)
    return {"filename": safe_name, "size_bytes": len(raw), "path": f"artifacts/{stem}"}


def _resolve_target_kind(handle, record_id: str) -> str:
    graph = handle.run_graph
    matches: list[str] = []
    if record_id in graph.nodes:
        matches.append("node")
    if record_id in graph.steps:
        matches.append("step")
    if record_id in graph.payloads:
        matches.append("payload")
    if not matches:
        raise KeyError(f"unknown record_id: {record_id}")
    if len(matches) > 1:
        raise ValueError(f"ambiguous record_id {record_id!r}: {matches}")
    return matches[0]


def _step_view(step) -> dict:
    return {
        "kind": "step",
        "id": step.step_id,
        "step_id": step.step_id,
        "input_node_ids": list(step.input_node_ids),
        "output_node_id": step.output_node_id,
        "metadata": dict(step.metadata),
    }


def _graph_counts(handle) -> dict[str, set[str]]:
    return {
        "nodes": set(handle.run_graph.nodes),
        "steps": set(handle.run_graph.steps),
        "payloads": set(handle.run_graph.payloads),
        "work_events": {event.event_id for event in handle.run_graph.work_events},
    }


def _maybe_append_or_save(*, store, handle, user_id: str | None, lane_id: str | None, before: dict[str, set[str]]) -> None:
    if user_id is None or lane_id is None or not hasattr(store, "append_batch"):
        store.save_run(handle)
        return
    store.append_batch(_build_append_batch(handle, user_id=user_id, lane_id=lane_id, before=before))


def _build_append_batch(handle, *, user_id: str, lane_id: str, before: dict[str, set[str]]) -> AppendBatch:
    records: list[GraphRecordEnvelope] = []

    for node_id in _new_ids(handle.run_graph.nodes, before, "nodes"):
        records.append(GraphRecordEnvelope("node", node_id, handle.run_graph.nodes[node_id]))
    for step_id in _new_ids(handle.run_graph.steps, before, "steps"):
        records.append(GraphRecordEnvelope("step", step_id, handle.run_graph.steps[step_id]))
    for payload_id in _new_ids(handle.run_graph.payloads, before, "payloads"):
        records.append(GraphRecordEnvelope("payload", payload_id, handle.run_graph.payloads[payload_id]))

    new_events = [event for event in handle.run_graph.work_events if event.event_id not in before.get("work_events", set())]
    if not new_events:
        raise RuntimeError("append batch requires at least one work event")

    session = handle.run_graph.lanes[lane_id]
    return AppendBatch(
        run_id=handle.run_id,
        user_id=user_id,
        lane_id=lane_id,
        lane=session,
        events=tuple(new_events),
        records=tuple(records),
    )


def _new_ids(current: dict[str, object], before: dict[str, set[str]], key: str) -> list[str]:
    return [record_id for record_id in current if record_id not in before.get(key, set())]
