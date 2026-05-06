"""Protocols for the rebuild architecture."""

from __future__ import annotations

from typing import Protocol

from optagent.core.derived import Evidence, Observation
from optagent.core.plans import ExecutionPlan, PredictionPlan
from optagent.core.results import ActionResult
from optagent.core.state import StateNode


class ExecutionPlanner(Protocol):
    """Proposes executable plans from an observed state."""

    def propose_execution(self, state: StateNode) -> list[ExecutionPlan]:
        ...


class PredictionPlanner(Protocol):
    """Proposes prediction plans from a predicted state."""

    def propose_prediction(self, state: StateNode) -> list[PredictionPlan]:
        ...


class Executor(Protocol):
    """Runs a grounded execution plan and returns raw execution results."""

    def execute(self, plan: ExecutionPlan) -> ActionResult:
        ...


class Evaluator(Protocol):
    """Converts observations into normalized evidence."""

    def evaluate(self, observation: Observation) -> Evidence:
        ...
