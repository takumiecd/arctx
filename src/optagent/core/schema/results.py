"""Execution result records."""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.types import JSONValue, ResultStatus, to_jsonable


@dataclass(frozen=True)
class ActionResult:
    """Artifacts and raw outputs produced by executing an ExecutionPlan."""

    result_id: str
    execution_plan_id: str
    status: ResultStatus
    artifacts: tuple[str, ...] = ()
    raw_outputs: tuple[str, ...] = ()
    logs: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    actual_cost: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
