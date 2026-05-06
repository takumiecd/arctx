"""Shared primitive types and JSON conversion helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Literal, TypeAlias


JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]

ActionType = Literal[
    "investigation",
    "implementation",
    "verification",
    "analysis",
    "scope_refinement",
]

StateKind = Literal["observed", "predicted"]
PlanKind = Literal["execution", "prediction"]
TransitionKind = Literal["observed", "predicted"]
MatchStatus = Literal["exact", "compatible", "partial", "mismatch"]
DecisionStatus = Literal[
    "accepted",
    "rejected",
    "needs_narrower_scope",
    "needs_more_evidence",
    "unsafe",
]

PlanStatus = Literal["active", "promoted", "executed", "stale", "pruned", "cancelled"]
NodeStatus = Literal["active", "stale", "pruned", "merged"]
ResultStatus = Literal["completed", "failed", "timeout", "skipped"]
DerivedType = Literal[
    "observation",
    "evidence",
    "prediction_error",
    "decision",
    "finding",
    "state_delta",
    "summary",
]


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
