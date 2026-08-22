"""Pure request dispatcher for the local ARCTX run API."""

from __future__ import annotations

import re
from typing import Any

from arctx.core.append import AppendBatch, GraphRecordEnvelope
from arctx.core.lanes import format_lane_validation_errors, lane_validation_errors
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
        if route == ("GET", "/asset"):
            return _get_asset(store, run_id, query or {})
        if route == ("GET", "/asset/entries"):
            return _get_asset_entries(store, run_id, query or {})
        if route == ("GET", "/asset/content"):
            return _get_asset_content(store, run_id, query or {})
        if route == ("GET", "/ext"):
            return 200, _get_ext(store, run_id)
        if route == ("POST", "/ext/enable"):
            return 200, _post_ext_enable(store, run_id, body or {})
        if route == ("POST", "/ext/disable"):
            return 200, _post_ext_disable(store, run_id, body or {})
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
    try:
        attached = handle.attach(target_id, payload, user_id=user_id, lane_id=lane_id)
    except KeyError as exc:
        raise ApiError(404, str(exc).strip("'")) from exc

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


# ---------------------------------------------------------------------------
# Assets — git object references resolved at request time
# ---------------------------------------------------------------------------


def _asset_args(store: Any, run_id: str, query: dict) -> tuple[Any, Any, str, str | None]:
    payload_id = query.get("payload_id") or query.get("asset")
    if not payload_id:
        raise ApiError(400, "payload_id is required")
    handle = _load(store, run_id)
    return handle, store.run_path(run_id), str(payload_id), query.get("path")


def _get_asset(store: Any, run_id: str, query: dict) -> tuple[int, dict]:
    from arctx.serve.assets import AssetError, asset_view

    handle, run_path, payload_id, _ = _asset_args(store, run_id, query)
    try:
        return 200, asset_view(handle, run_path, payload_id)
    except AssetError as exc:
        return exc.status, {"error": exc.message, "code": exc.code}


def _get_asset_entries(store: Any, run_id: str, query: dict) -> tuple[int, dict]:
    from arctx.serve.assets import AssetError, asset_entries

    handle, run_path, payload_id, sub_path = _asset_args(store, run_id, query)
    try:
        return 200, asset_entries(handle, run_path, payload_id, sub_path)
    except AssetError as exc:
        return exc.status, {"error": exc.message, "code": exc.code}


def _get_asset_content(store: Any, run_id: str, query: dict) -> tuple[int, dict]:
    from arctx.serve.assets import AssetError, asset_content

    handle, run_path, payload_id, sub_path = _asset_args(store, run_id, query)
    try:
        return 200, asset_content(handle, run_path, payload_id, sub_path)
    except AssetError as exc:
        return exc.status, {"error": exc.message, "code": exc.code}


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
