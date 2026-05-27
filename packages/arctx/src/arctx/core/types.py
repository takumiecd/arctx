"""Shared primitive types and JSON conversion helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Literal

JSONValue = Any

TargetKind = Literal["node", "transition"]

NODE_PREFIX = "n"
TRANSITION_PREFIX = "t"
PAYLOAD_PREFIX = "pl"


def to_jsonable(value: Any) -> JSONValue:
    """Convert dataclass records and paths into JSON-friendly values."""
    if is_dataclass(value):
        return {str(k): to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)
