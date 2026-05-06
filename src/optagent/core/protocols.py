"""Protocols for the rebuild architecture."""

from __future__ import annotations

from typing import Protocol

from optagent.core.schema import ActionResult, ActionSpec, Evidence, Observation, StateNode


class SearchPolicy(Protocol):
    """Proposes one or more actions from a state."""

    def propose(self, state: StateNode) -> list[ActionSpec]:
        ...


class Executor(Protocol):
    """Runs an action and returns raw execution results."""

    def execute(self, action: ActionSpec) -> ActionResult:
        ...


class Evaluator(Protocol):
    """Converts observations into normalized evidence."""

    def evaluate(self, observation: Observation) -> Evidence:
        ...
