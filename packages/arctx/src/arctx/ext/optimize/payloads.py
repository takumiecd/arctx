"""Trial records for the optimize extension.

A trial is one scored attempt: a step annotated with the configuration that
was tried and the metric values that came out. The record holds *facts* only —
table names, config values, metric values. Which tables exist, their columns,
column kinds, sort orders, and best rows are all derived from the rows at read
time (:mod:`arctx.ext.optimize.tables`); no table-definition record exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from arctx.core.schema.payloads import (
    PayloadBase,
    register_payload_class,
    register_payload_decoder,
)
from arctx.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class TrialPayload(PayloadBase):
    """One scored trial on a Step.

    ``tables`` are plain shared names, like lane names or git branch names: a
    "table" is nothing but the set of trials that carry its name. A trial may
    belong to several tables; membership lives on each row, so appending a row
    never touches any other record.
    """

    payload_id: str
    target_id: str
    tables: tuple[str, ...]
    config: dict[str, JSONValue] = field(default_factory=dict)
    metrics: dict[str, JSONValue] = field(default_factory=dict)
    title: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["step"] = field(default="step", init=False)
    payload_type: str = field(default="trial", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


def _trial_from_dict(data: dict[str, JSONValue]) -> TrialPayload:
    tables = data.get("tables") or ()
    return TrialPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        tables=tuple(str(name) for name in tables),
        config=dict(data.get("config") or {}),
        metrics=dict(data.get("metrics") or {}),
        title=None if data.get("title") is None else str(data["title"]),
        metadata=dict(data.get("metadata") or {}),
    )


register_payload_class(TrialPayload)
register_payload_decoder("trial", _trial_from_dict)

__all__ = ["TrialPayload"]
