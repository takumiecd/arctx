"""Pure request dispatcher for ``arctx serve``.

Socket-free by design: every route is a plain ``(method, path, body) ->
(status, dict)`` mapping, so the whole API surface can be exercised in unit
tests without binding a port. The HTTP shell in :mod:`arctx_cli.serve.server`
only translates bytes to/from this function.

Routes (the GUI data contract):

- ``GET  /health``  -> ``{"status": "ok", "run_id": ...}``
- ``GET  /run``     -> the full :func:`arctx.core.run.export.json_document`
- ``POST /step``    -> create a Step from input nodes; returns the new step
- ``POST /attach``  -> attach a node payload; returns the new payload
- ``POST /cut``     -> cut a node or step; returns the cut payload

Write routes reuse the exact same building blocks as the ``arctx add`` /
``arctx cut`` CLI commands (``build_payload`` + ``maybe_append_or_save``) so
the HTTP surface and the CLI can never drift in how records are written.
"""

from __future__ import annotations

from typing import Any

from arctx.core.run.export import ExportOptions, json_document
from arctx.payload_builder import build_payload

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.commands._targets import step_view


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
) -> tuple[int, dict]:
    """Route one request to a handler and return ``(status, body_dict)``.

    Never raises for client-facing errors: :class:`ApiError`, missing runs,
    and bad input all become a ``{"error": ...}`` body with an appropriate
    status code.
    """
    route = (method.upper(), path.rstrip("/") or "/")
    try:
        if route == ("GET", "/health"):
            return 200, {"status": "ok", "run_id": run_id}
        if route == ("GET", "/run"):
            return 200, _get_run(store, run_id)
        if route == ("POST", "/step"):
            return 201, _post_step(store, run_id, body or {}, user_id, work_session_id)
        if route == ("POST", "/attach"):
            return 201, _post_attach(store, run_id, body or {}, user_id, work_session_id)
        if route == ("POST", "/cut"):
            return 201, _post_cut(store, run_id, body or {}, user_id, work_session_id)
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


def _get_run(store: Any, run_id: str) -> dict:
    handle = _load(store, run_id)
    return json_document(handle, ExportOptions())


def _payload_fields(body: dict) -> dict:
    """Pull the payload-shaping fields out of a request body."""
    data: dict = {}
    if body.get("type") is not None:
        data["type"] = body["type"]
    if body.get("content") is not None:
        data["content"] = body["content"]
    if body.get("metadata") is not None:
        data["metadata"] = body["metadata"]
    return data


def _post_step(store, run_id, body, user_id, work_session_id) -> dict:
    inputs = body.get("input_node_ids")
    if not isinstance(inputs, list) or not inputs:
        raise ApiError(400, "input_node_ids must be a non-empty list")

    handle = _load(store, run_id)
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
        user_id=user_id,
        work_session_id=work_session_id,
    )
    maybe_append_or_save(
        store=store, handle=handle,
        user_id=user_id, work_session_id=work_session_id, before=before,
    )
    return {"step": step_view(step)}


def _post_attach(store, run_id, body, user_id, work_session_id) -> dict:
    node_id = body.get("node_id")
    if not node_id:
        raise ApiError(400, "node_id is required")

    handle = _load(store, run_id)
    payload = build_payload(
        payload_type=str(body.get("payload_type", "node_payload")),
        target_kind="node",
        target_id="pending",
        payload_id="pending",
        json_data=_payload_fields(body),
    )
    before = graph_counts(handle)
    attached = handle.attach(
        str(node_id), payload,
        user_id=user_id, work_session_id=work_session_id,
    )
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
