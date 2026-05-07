"""PredictionDAG and TraceDAG indexes.

``node_depths`` / ``nodes_by_depth`` are kept for storage and display
compatibility but are *not* the source of truth for correctness checks
(rewind, ancestor relationships, plan creation). Treat them as derived
indexes scheduled for deprecation; new logic must use the incoming-edge
walks instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.schema.plans import ExecutionPlan, PredictionPlan
from optagent.core.schema.state import StateNode
from optagent.core.schema.transitions import ObservedTransition, PredictedTransition
from optagent.core.types import to_jsonable


@dataclass
class PredictionDAG:
    """Unexecuted future expansion grouped by depth.

    The DAG owns future-facing indexes. A plan may have multiple predicted
    transitions because one intended action can have several plausible outcomes.
    """

    dag_id: str
    anchor_observed_state_id: str
    root_predicted_state_id: str
    nodes: dict[str, StateNode] = field(default_factory=dict)
    node_depths: dict[str, int] = field(default_factory=dict)
    nodes_by_depth: dict[int, list[str]] = field(default_factory=dict)
    plans: dict[str, PredictionPlan] = field(default_factory=dict)
    transitions: dict[str, PredictedTransition] = field(default_factory=dict)
    plans_by_state: dict[str, list[str]] = field(default_factory=dict)
    transitions_by_plan: dict[str, list[str]] = field(default_factory=dict)
    outgoing_index: dict[str, list[str]] = field(default_factory=dict)
    incoming_index: dict[str, list[str]] = field(default_factory=dict)
    stale: bool = False

    def add_node(self, node: StateNode, depth: int) -> None:
        self.nodes[node.state_id] = node
        self.node_depths[node.state_id] = depth
        self.nodes_by_depth.setdefault(depth, []).append(node.state_id)

    def add_plan(self, plan: PredictionPlan) -> None:
        self.plans[plan.plan_id] = plan
        self.plans_by_state.setdefault(plan.from_predicted_state_id, []).append(plan.plan_id)

    def add_transition(self, transition: PredictedTransition) -> None:
        self.transitions[transition.transition_id] = transition
        self.transitions_by_plan.setdefault(transition.parent_plan_id, []).append(
            transition.transition_id
        )
        self.outgoing_index.setdefault(transition.from_state_id, []).append(
            transition.transition_id
        )
        self.incoming_index.setdefault(transition.to_predicted_state_id, []).append(
            transition.transition_id
        )

    def depth(self, depth: int) -> list[StateNode]:
        return [self.nodes[state_id] for state_id in self.nodes_by_depth.get(depth, ())]

    def future_transition_ids(self, state_id: str) -> list[str]:
        return list(self.outgoing_index.get(state_id, ()))

    def plan_ids_from_state(self, state_id: str) -> list[str]:
        return list(self.plans_by_state.get(state_id, ()))

    def predicted_transition_ids_for_plan(self, plan_id: str) -> list[str]:
        return list(self.transitions_by_plan.get(plan_id, ()))

    def to_dict(self) -> dict:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass
class TraceDAG:
    """Observed execution history grouped by depth.

    The TraceDAG is source-of-truth history. Observed transitions are append-only
    records that connect an execution plan, an action result, and optional
    derived records.
    """

    dag_id: str
    nodes: dict[str, StateNode] = field(default_factory=dict)
    node_depths: dict[str, int] = field(default_factory=dict)
    nodes_by_depth: dict[int, list[str]] = field(default_factory=dict)
    execution_plans: dict[str, ExecutionPlan] = field(default_factory=dict)
    transitions: dict[str, ObservedTransition] = field(default_factory=dict)
    plans_by_state: dict[str, list[str]] = field(default_factory=dict)
    transition_by_execution_plan: dict[str, str] = field(default_factory=dict)
    outgoing_index: dict[str, list[str]] = field(default_factory=dict)
    incoming_index: dict[str, list[str]] = field(default_factory=dict)

    def add_node(self, node: StateNode, depth: int) -> None:
        self.nodes[node.state_id] = node
        self.node_depths[node.state_id] = depth
        self.nodes_by_depth.setdefault(depth, []).append(node.state_id)

    def add_execution_plan(self, plan: ExecutionPlan) -> None:
        self.execution_plans[plan.plan_id] = plan
        self.plans_by_state.setdefault(plan.from_observed_state_id, []).append(
            plan.plan_id
        )

    def append_transition(self, transition: ObservedTransition) -> None:
        if transition.execution_plan_id in self.transition_by_execution_plan:
            raise ValueError(
                "an ExecutionPlan can have only one ObservedTransition; "
                "create a new ExecutionPlan to rerun the same operation"
            )
        self.transitions[transition.transition_id] = transition
        self.transition_by_execution_plan[transition.execution_plan_id] = (
            transition.transition_id
        )
        self.outgoing_index.setdefault(transition.from_observed_state_id, []).append(
            transition.transition_id
        )
        self.incoming_index.setdefault(transition.to_observed_state_id, []).append(
            transition.transition_id
        )

    def depth(self, depth: int) -> list[StateNode]:
        return [self.nodes[state_id] for state_id in self.nodes_by_depth.get(depth, ())]

    def past_transition_ids(self, state_id: str) -> list[str]:
        return list(self.incoming_index.get(state_id, ()))

    def next_transition_ids(self, state_id: str) -> list[str]:
        return list(self.outgoing_index.get(state_id, ()))

    def ancestors_of(self, state_id: str) -> tuple[str, ...]:
        """Return observed state_ids reachable backwards via incoming edges.

        Order is BFS from *state_id* (closest ancestor first). The starting
        state itself is not included.
        """
        seen: set[str] = set()
        order: list[str] = []
        frontier: list[str] = [state_id]
        while frontier:
            current = frontier.pop(0)
            for tid in self.incoming_index.get(current, ()):
                parent = self.transitions[tid].from_observed_state_id
                if parent in seen:
                    continue
                seen.add(parent)
                order.append(parent)
                frontier.append(parent)
        return tuple(order)

    def is_ancestor(self, ancestor_id: str, descendant_id: str) -> bool:
        """Return True iff *ancestor_id* lies on a backwards path from *descendant_id*.

        A state is treated as an ancestor of itself.
        """
        if ancestor_id == descendant_id:
            return True
        return ancestor_id in self.ancestors_of(descendant_id)

    def plan_ids_from_state(self, state_id: str) -> list[str]:
        return list(self.plans_by_state.get(state_id, ()))

    def to_dict(self) -> dict:
        return to_jsonable(self)  # type: ignore[return-value]
