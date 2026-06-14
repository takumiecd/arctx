"""Helpers for constructing payloads from CLI arguments."""

from __future__ import annotations

import json
from dataclasses import MISSING, fields, is_dataclass
from typing import Literal

from arctx.core.schema.payloads import (
    CutPayload,
    NodePayload,
    PayloadBase,
    StepPayload,
    _PAYLOAD_REGISTRY,
    payload_from_dict,
)
from arctx.core.types import JSONValue


def parse_json_object(raw: str | None) -> dict[str, JSONValue]:
    if raw is None:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("--json must be a JSON object")
    return data


def parse_field_args(items: list[str] | None) -> dict[str, JSONValue]:
    parsed: dict[str, JSONValue] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"--field must be key=value: {item}")
        key, raw_value = item.split("=", 1)
        if not key:
            raise ValueError(f"--field key cannot be empty: {item}")
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value
        parsed[key] = value
    return parsed


def payload_type_names() -> list[str]:
    return sorted(_PAYLOAD_REGISTRY)


def payload_schema(payload_type: str) -> dict[str, JSONValue]:
    cls = _PAYLOAD_REGISTRY.get(payload_type)
    if cls is None:
        return {
            "payload_type": payload_type,
            "registered": False,
            "fields": {},
        }
    schema_fields: dict[str, dict[str, JSONValue]] = {}
    if is_dataclass(cls):
        for f in fields(cls):  # type: ignore[arg-type]
            if not f.init:
                continue
            schema_fields[f.name] = {
                "required": f.default is MISSING and f.default_factory is MISSING,
                "type": str(f.type),
            }
    target_kind = getattr(cls, "target_kind", None)
    return {
        "payload_type": payload_type,
        "registered": True,
        "target_kind": target_kind if isinstance(target_kind, str) else None,
        "fields": schema_fields,
    }


def build_payload(
    *,
    payload_type: str,
    target_kind: Literal["node", "step"],
    target_id: str,
    payload_id: str,
    json_data: dict[str, JSONValue] | None = None,
    field_data: dict[str, JSONValue] | None = None,
) -> PayloadBase:
    data = dict(json_data or {})
    data.update(field_data or {})

    if payload_type == "node_payload":
        if target_kind != "node":
            raise ValueError("node_payload can only target a node")
        payload_kind = str(data.pop("type", "payload"))
        metadata = _dict_field(data.pop("metadata", {}), "metadata")
        content = _dict_field(data.pop("content", {}), "content")
        content.update(data)
        return NodePayload(
            payload_id=payload_id,
            target_id=target_id,
            type=payload_kind,
            content=content,
            metadata=metadata,
        )

    if payload_type == "step_payload":
        if target_kind != "step":
            raise ValueError("step_payload can only target a step")
        payload_kind = str(data.pop("type", "payload"))
        metadata = _dict_field(data.pop("metadata", {}), "metadata")
        content = _dict_field(data.pop("content", {}), "content")
        content.update(data)
        return StepPayload(
            payload_id=payload_id,
            target_id=target_id,
            type=payload_kind,
            content=content,
            metadata=metadata,
        )

    if payload_type == "cut":
        reason = data.pop("reason", None)
        metadata = _dict_field(data.pop("metadata", {}), "metadata")
        if data:
            metadata.update(data)
        return CutPayload(
            payload_id=payload_id,
            target_id=target_id,
            target_kind=target_kind,
            reason=None if reason is None else str(reason),
            metadata=metadata,
        )

    if payload_type == "git_change":
        if target_kind != "step":
            raise ValueError("git_change can only target a step")
        raise ValueError("use 'arctx git add' to attach git_change payloads")

    raw = {
        "payload_id": payload_id,
        "payload_type": payload_type,
        "target_kind": target_kind,
        "target_id": target_id,
        **data,
    }
    payload = payload_from_dict(raw)
    if payload.payload_type == "git_change":
        raise ValueError("use 'arctx git add' to attach git_change payloads")
    return payload


def _dict_field(value: JSONValue, name: str) -> dict[str, JSONValue]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return dict(value)
