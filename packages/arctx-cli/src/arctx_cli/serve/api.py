"""Pure request dispatcher for ``arctx serve``.

Socket-free by design: every route is a plain ``(method, path, body) ->
(status, dict)`` mapping, so the whole API surface can be exercised in unit
tests without binding a port. The HTTP shell in :mod:`arctx_cli.serve.server`
only translates bytes to/from this function.

Routes (the GUI data contract):

- ``GET  /health``  -> ``{"status": "ok", "run_id": ...}``
- ``GET  /runs``    -> list available runs in the store (for the GUI run picker)
- ``POST /runs``    -> create a new run; returns its summary
- ``GET  /run``     -> the full :func:`arctx.core.run.export.json_document`
- ``POST /step``    -> create a Step from input nodes; returns the new step
- ``POST /attach``  -> attach a payload to a Node or Step; returns the payload
- ``POST /cut``     -> cut a node or step; returns the cut payload
- ``POST /uncut``   -> reverse a cut on a node or step; returns the uncut payload
- ``POST /reparent`` -> re-parent a node onto new inputs; returns the new step
- ``POST /lane``    -> create a lane
- ``POST /lane/adopt`` -> adopt existing records into a lane

Write routes reuse the exact same building blocks as the ``arctx add`` /
``arctx attach`` / ``arctx cut`` CLI commands (``build_payload`` +
``maybe_append_or_save``) so the HTTP surface and the CLI can never drift in
how records are written.
"""

from __future__ import annotations

import re
from typing import Any

from arctx.core.lanes import (
    LaneValidationIssue,
    format_lane_validation_errors,
    lane_membership,
    lane_validation_errors,
)
from arctx.core.run.export import ExportOptions, json_document
from arctx.payload_builder import build_payload

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.commands._targets import resolve_target_kind, step_view


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
    work_session_id: str,
    query: dict | None = None,
) -> tuple[int, dict]:
    """Route one request to a handler and return ``(status, body_dict)``.

    Never raises for client-facing errors: :class:`ApiError`, missing runs,
    and bad input all become a ``{"error": ...}`` body with an appropriate
    status code.

    ``query`` carries parsed URL query parameters (values flattened to the
    first occurrence); read routes that need them pull from it.
    """
    route = (method.upper(), path.rstrip("/") or "/")
    try:
        if route == ("GET", "/health"):
            return 200, {"status": "ok", "run_id": run_id}
        if route == ("GET", "/runs"):
            return 200, {"runs": store.list_runs(), "current_run_id": run_id}
        if route == ("POST", "/runs"):
            return 201, _post_runs(store, body or {})
        if route == ("GET", "/run"):
            return 200, _get_run(store, run_id, work_session_id)
        if route == ("GET", "/assets/visible"):
            return 200, _get_visible_assets(store, run_id, query or {})
        if route == ("POST", "/step"):
            return 201, _post_step(store, run_id, body or {}, user_id, work_session_id)
        if route == ("POST", "/attach"):
            return 201, _post_attach(store, run_id, body or {}, user_id, work_session_id)
        if route == ("POST", "/cut"):
            return 201, _post_cut(store, run_id, body or {}, user_id, work_session_id)
        if route == ("POST", "/uncut"):
            return 201, _post_uncut(store, run_id, body or {}, user_id, work_session_id)
        if route == ("POST", "/reparent"):
            return 201, _post_reparent(store, run_id, body or {}, user_id, work_session_id)
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


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _load(store: Any, run_id: str):
    if not store.run_path(run_id).exists():
        raise ApiError(404, f"unknown run_id: {run_id}")
    return store.load_run(run_id)


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _post_runs(store: Any, body: dict) -> dict:
    """Create a new run in the store and return its summary.

    The GUI sends a human-chosen ``run_id`` (the directory name), so it is
    validated against a conservative charset to prevent path traversal. Other
    requirement fields fall back to the run id, matching ``arctx init``'s
    defaults (target_type ``code``).
    """
    import arctx as arctx
    from arctx.core.schema.requirements import Requirement

    raw_id = body.get("run_id") or body.get("name")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise ApiError(400, "run_id (or name) is required")
    run_id = raw_id.strip()
    if run_id in (".", "..") or not _RUN_ID_RE.match(run_id):
        raise ApiError(
            400,
            "run_id may contain only letters, digits, '.', '_' and '-'",
        )
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


def _get_run(store: Any, run_id: str, work_session_id: str) -> dict:
    handle = _load(store, run_id)
    doc = json_document(handle, ExportOptions())
    lane = handle.run_graph.work_sessions.get(work_session_id)
    doc["current_lane_id"] = work_session_id
    doc["current_lane_name"] = lane.name if lane is not None else work_session_id
    return doc


def _get_visible_assets(store: Any, run_id: str, query: dict) -> dict:
    """List asset payloads referenceable from a given record.

    ``from`` (a node or step id) is the viewer; an asset is returned when its
    target is an ancestor of the viewer or the viewer itself (parents OK,
    children excluded). Lineage is computed in :mod:`arctx.core.lineage`.
    """
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
            # Asset attached to a record no longer in the graph; skip.
            continue
    return {"from": from_id, "assets": assets}


def _payload_fields(body: dict) -> dict:
    """Pull the payload-shaping fields out of a request body."""
    exclude = {
        "payload_type", "target_id", "target_kind", "node_id",
        "input_node_ids", "output_node_id", "reason",
    }
    return {k: v for k, v in body.items() if k not in exclude}


def _post_step(store, run_id, body, user_id, work_session_id) -> dict:
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
    before = graph_counts(handle)
    step = handle.add_step(
        [str(n) for n in inputs],
        payload,
        output_node_id=str(output_node_id) if output_node_id else None,
        user_id=user_id,
        work_session_id=work_session_id,
    )
    _ensure_lane_integrity(handle, baseline=baseline)
    maybe_append_or_save(
        store=store, handle=handle,
        user_id=user_id, work_session_id=work_session_id, before=before,
    )
    return {"step": step_view(step)}


def _post_attach(store, run_id, body, user_id, work_session_id) -> dict:
    """Attach a payload to a Node or Step.

    Accepts ``target_id`` (preferred) or the legacy ``node_id``. The target
    kind is taken from ``target_kind`` if given, else resolved from the record
    id. Node targets go through ``handle.attach`` (active-node validation);
    step targets mirror ``arctx payload add`` (run_graph.attach_payload + a
    work event) since core's attach verb is node-only.
    """
    target_id = body.get("target_id") or body.get("node_id")
    if not target_id:
        raise ApiError(400, "target_id is required")
    target_id = str(target_id)

    handle = _load(store, run_id)
    target_kind = body.get("target_kind")
    if target_kind not in ("node", "step"):
        target_kind = resolve_target_kind(handle, target_id)
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

    before = graph_counts(handle)
    if target_kind == "node":
        attached = handle.attach(
            target_id, payload,
            user_id=user_id, work_session_id=work_session_id,
        )
    else:
        if target_id not in handle.run_graph.steps:
            raise ApiError(404, f"unknown step_id: {target_id}")
        handle.run_graph.attach_payload(payload)
        handle.record_work_event(
            user_id=user_id, work_session_id=work_session_id,
            event_type="payload_attached", target_kind="step",
            target_id=target_id, created_records=(payload.payload_id,),
            summary=payload.payload_type,
        )
        attached = payload

    maybe_append_or_save(
        store=store, handle=handle,
        user_id=user_id, work_session_id=work_session_id, before=before,
    )
    return {"payload": attached.to_dict()}


def _post_cut(store, run_id, body, user_id, work_session_id) -> dict:
    target_id = body.get("target_id")
    target_kind = body.get("target_kind")
    if not target_id:
        raise ApiError(400, "target_id is required")
    if target_kind not in ("node", "step"):
        raise ApiError(400, "target_kind must be 'node' or 'step'")

    handle = _load(store, run_id)
    before = graph_counts(handle)
    cut = handle.cut(
        str(target_id),
        target_kind=target_kind,
        reason=body.get("reason"),
        user_id=user_id,
        work_session_id=work_session_id,
    )
    maybe_append_or_save(
        store=store, handle=handle,
        user_id=user_id, work_session_id=work_session_id, before=before,
    )
    return {"payload": cut.to_dict()}


def _post_uncut(store, run_id, body, user_id, work_session_id) -> dict:
    target_id = body.get("target_id")
    target_kind = body.get("target_kind")
    if not target_id:
        raise ApiError(400, "target_id is required")
    if target_kind not in ("node", "step"):
        raise ApiError(400, "target_kind must be 'node' or 'step'")

    handle = _load(store, run_id)
    before = graph_counts(handle)
    uncut = handle.uncut(
        str(target_id),
        target_kind=target_kind,
        reason=body.get("reason"),
        user_id=user_id,
        work_session_id=work_session_id,
    )
    maybe_append_or_save(
        store=store, handle=handle,
        user_id=user_id, work_session_id=work_session_id, before=before,
    )
    return {"payload": uncut.to_dict()}


def _post_reparent(store, run_id, body, user_id, work_session_id) -> dict:
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
    before = graph_counts(handle)
    step = handle.reparent(
        str(node_id),
        [str(n) for n in inputs],
        payload,
        reason=body.get("reason"),
        user_id=user_id,
        work_session_id=work_session_id,
    )
    _ensure_lane_integrity(handle, baseline=baseline)
    maybe_append_or_save(
        store=store, handle=handle,
        user_id=user_id, work_session_id=work_session_id, before=before,
    )
    return {"step": step_view(step)}


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
        lane = next(
            (
                candidate
                for candidate in handle.run_graph.lanes.values()
                if candidate.name == lane_ref
            ),
            None,
        )
    if lane is None:
        raise ApiError(404, f"unknown lane: {lane_ref}")

    ids, mode, target_id = _adoption_record_ids(handle, body)
    before = graph_counts(handle)
    event = handle.adopt_lane_records(
        lane.work_session_id,
        ids,
        user_id=user_id,
        mode=mode,
        target_id=target_id,
        reason=body.get("reason") if isinstance(body.get("reason"), str) else None,
    )
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=lane.work_session_id,
        before=before,
    )
    return {
        "lane_id": lane.work_session_id,
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
        raise ApiError(
            400,
            (
                "choose exactly one of record_ids, history_node_id, "
                "reachable_node_id, lane_head_node_id, lane_tail_node_id"
            ),
        )

    if isinstance(record_ids, list) and record_ids:
        ids = tuple(dict.fromkeys(str(record_id) for record_id in record_ids))
        return ids, "explicit", ids[0]

    if history_node_id is not None:
        node_id = str(history_node_id)
        if node_id not in handle.run_graph.nodes:
            raise ApiError(404, f"unknown node_id: {node_id}")
        trace = handle.trace(node_id)
        ids = (
            trace.past_node_ids
            + (trace.current_node_id,)
            + trace.step_ids
            + trace.payload_ids
        )
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
        producer_step_ids
        + (node_id,)
        + tuple(reachable["node_ids"])
        + tuple(reachable["step_ids"])
        + tuple(reachable["payload_ids"])
    )
    return _without_run_root(handle, ids), "reachable", node_id


def _lane_local_head_record_ids(handle, node_id: str) -> tuple[str, ...]:
    graph = handle.run_graph
    if node_id not in graph.nodes:
        raise ApiError(404, f"unknown node_id: {node_id}")
    membership = lane_membership(graph, root_node_id=handle.root_node_id)
    lane_id = membership.node_to_lane.get(node_id)
    if lane_id is None:
        raise ApiError(400, f"node has no lane membership: {node_id}")

    node_ids: set[str] = set()
    step_ids: set[str] = set()

    def visit_node(nid: str) -> None:
        if nid in node_ids or membership.node_to_lane.get(nid) != lane_id:
            return
        node_ids.add(nid)
        producer = graph.step_to_node(nid)
        if producer is None or membership.step_to_lane.get(producer) != lane_id:
            return
        step_ids.add(producer)
        for parent_id in graph.steps[producer].input_node_ids:
            visit_node(parent_id)

    visit_node(node_id)
    return _with_payloads(graph, node_ids=node_ids, step_ids=step_ids)


def _lane_local_tail_record_ids(handle, node_id: str) -> tuple[str, ...]:
    graph = handle.run_graph
    if node_id not in graph.nodes:
        raise ApiError(404, f"unknown node_id: {node_id}")
    membership = lane_membership(graph, root_node_id=handle.root_node_id)
    lane_id = membership.node_to_lane.get(node_id)
    if lane_id is None:
        raise ApiError(400, f"node has no lane membership: {node_id}")

    node_ids: set[str] = set()
    step_ids: set[str] = set()

    def include_producer(nid: str) -> None:
        producer = graph.step_to_node(nid)
        if producer is not None and membership.step_to_lane.get(producer) == lane_id:
            step_ids.add(producer)

    def visit_node(nid: str) -> None:
        if nid in node_ids or membership.node_to_lane.get(nid) != lane_id:
            return
        node_ids.add(nid)
        include_producer(nid)
        for step_id in graph.steps_from_node(nid):
            if membership.step_to_lane.get(step_id) != lane_id:
                continue
            out = graph.step_output(step_id)
            if out and membership.node_to_lane.get(out) == lane_id:
                step_ids.add(step_id)
                visit_node(out)

    visit_node(node_id)
    return _with_payloads(graph, node_ids=node_ids, step_ids=step_ids)


def _with_payloads(graph, *, node_ids: set[str], step_ids: set[str]) -> tuple[str, ...]:
    payload_ids: list[str] = []
    for node_id in sorted(node_ids):
        payload_ids.extend(graph.payloads_by_node.get(node_id, ()))
    for step_id in sorted(step_ids):
        payload_ids.extend(graph.payloads_by_step.get(step_id, ()))
    return tuple(sorted(node_ids) + sorted(step_ids) + sorted(set(payload_ids)))


def _without_run_root(handle, ids) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(record_id)
            for record_id in ids
            if str(record_id) != handle.root_node_id
        )
    )


def _issue_key(issue: LaneValidationIssue) -> tuple[str, str | None, str | None]:
    """Stable identity for a lane validation issue (ignores volatile counts)."""
    return (issue.code, issue.record_id, issue.lane_id)


def _lane_error_baseline(handle) -> frozenset[tuple[str, str | None, str | None]]:
    """Capture pre-existing lane errors so writes are judged by their delta.

    Legacy runs created before lane provenance existed carry records with no
    lane membership. Those errors are not this write's fault, so we record them
    up front and only block on errors the current write introduces.
    """
    return frozenset(
        _issue_key(issue)
        for issue in lane_validation_errors(
            handle.run_graph, root_node_id=handle.root_node_id
        )
    )


def _ensure_lane_integrity(
    handle,
    *,
    baseline: frozenset[tuple[str, str | None, str | None]] | None = None,
) -> None:
    """Reject a write that introduces new lane invariant violations.

    With ``baseline`` (the errors present before the write), pre-existing
    violations on legacy runs are tolerated; only newly-introduced errors
    block the write. Without it, every error blocks.
    """
    errors = lane_validation_errors(handle.run_graph, root_node_id=handle.root_node_id)
    if baseline is not None:
        errors = tuple(
            issue for issue in errors if _issue_key(issue) not in baseline
        )
    if errors:
        raise ValueError(format_lane_validation_errors(errors))


def _get_ext(store, run_id) -> dict:
    from arctx_cli.commands.ext import run_ext_list_command
    run_dir = str(store.run_path(run_id))
    return run_ext_list_command(run_dir=run_dir)


def _post_ext_enable(store, run_id, body) -> dict:
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ApiError(400, "name is required")
    from arctx_cli.commands.ext import run_ext_enable_command
    run_dir = str(store.run_path(run_id))
    return run_ext_enable_command(name=name.strip(), run_dir=run_dir)


def _post_ext_disable(store, run_id, body) -> dict:
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ApiError(400, "name is required")
    from arctx_cli.commands.ext import run_ext_disable_command
    run_dir = str(store.run_path(run_id))
    return run_ext_disable_command(name=name.strip(), run_dir=run_dir)


def _post_artifacts_upload(store, run_id, body) -> dict:
    import base64
    import mimetypes
    import os
    from arctx.core.ids import opaque_id

    if not store.run_path(run_id).exists():
        raise ApiError(404, f"unknown run_id: {run_id}")

    filename = body.get("filename")
    file_data_b64 = body.get("file_data")
    if not filename or not file_data_b64:
        raise ApiError(400, "filename and file_data are required")

    # Only keep the basename: prevents path traversal and nested writes
    # (the destination is always a flat file directly under artifacts/).
    safe_name = os.path.basename(str(filename))
    if safe_name in ("", ".", ".."):
        raise ApiError(400, "invalid filename")

    try:
        file_content = base64.b64decode(file_data_b64)
    except Exception as exc:
        raise ApiError(400, f"invalid base64 data: {exc}")

    art_id = opaque_id("art")
    run_dir = store.run_path(run_id)
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    dest_filename = f"{art_id}_{safe_name}"
    dest_path = artifacts_dir / dest_filename
    dest_path.write_bytes(file_content)

    mime_type, _ = mimetypes.guess_type(safe_name)
    if not mime_type:
        mime_type = "application/octet-stream"

    return {
        "artifact_id": art_id,
        "filename": safe_name,
        "mime_type": mime_type,
        "size_bytes": len(file_content),
        "path": f"artifacts/{dest_filename}",
    }
