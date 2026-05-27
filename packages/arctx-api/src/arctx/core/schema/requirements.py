"""Run requirements."""

from __future__ import annotations

from dataclasses import dataclass, field

from arctx.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class Requirement:
    """Fixed optimization or problem-solving target for a run."""

    requirement_id: str
    target_type: str
    target_id: str
    objective: dict[str, JSONValue] = field(default_factory=dict)
    constraints: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]
