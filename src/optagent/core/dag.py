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
from optagent.core.schema.transitions import (
    ObservedTransition,
    PredictedTransition,
    TraceCut,
)
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
    cuts: dict[str, TraceCut] = field(default_factory=dict)
    cut_order: list[str] = field(default_factory=list)

    def add_node(self, node: StateNode, depth: int) -> None:
        self.nodes[node.state_id] = node
        self.node_depths[node.state_id] = depth
        self.nodes_by_depth.setdefault(depth, []).append(node.state_id)

    def add_cut(self, cut: TraceCut) -> None:
        """Append a ``TraceCut`` record. Append-only — never replaces an existing cut."""
        if cut.cut_id in self.cuts:
            raise ValueError(f"duplicate cut_id: {cut.cut_id}")
        if cut.cut_transition_id not in self.transitions:
            raise KeyError(f"unknown cut_transition_id: {cut.cut_transition_id}")
        self.cuts[cut.cut_id] = cut
        self.cut_order.append(cut.cut_id)

    def cut_transition_ids(self) -> set[str]:
        """Set of observed transitions that have been cut (latest event wins).

        With only ``TraceCut`` events today, the result is the union of
        ``cut.cut_transition_id`` across all recorded cuts. A future
        ``TraceRestore`` event would remove its target from the set
        when it is the latest event for that transition.
        """
        return {self.cuts[cid].cut_transition_id for cid in self.cut_order}

    def is_cut_transition(self, transition_id: str) -> bool:
        """True iff *transition_id* is a directly-cut edge (not just downstream)."""
        return transition_id in self.cut_transition_ids()

    def cut_state_ids(self) -> set[str]:
        """All observed state_ids reachable forward from any cut transition.

        These are the states whose only path from the trace root passes
        through a cut edge — i.e. they are no longer on any active branch.
        """
        cut_tids = self.cut_transition_ids()
        if not cut_tids:
            return set()
        cut_states: set[str] = set()
        frontier = [self.transitions[tid].to_observed_state_id for tid in cut_tids]
        while frontier:
            sid = frontier.pop()
            if sid in cut_states:
                continue
            cut_states.add(sid)
            for tid in self.outgoing_index.get(sid, ()):
                frontier.append(self.transitions[tid].to_observed_state_id)
        return cut_states

    def is_cut_state(self, state_id: str) -> bool:
        return state_id in self.cut_state_ids()

    def inactive_transition_ids(self) -> set[str]:
        """Every observed transition that is no longer on an active branch.

        This is the union of:
          - transitions directly named by a ``TraceCut`` (``cut_transition_ids``)
          - transitions that originate from a state inside a cut subtree
            (their ``from_observed_state_id`` is in ``cut_state_ids``)

        Use this when filtering for live records (UI, replay, planning).
        ``cut_transition_ids()`` alone names only the cut boundary, not
        the downstream edges that became inactive as a result.
        """
        inactive = set(self.cut_transition_ids())
        cut_states = self.cut_state_ids()
        for sid in cut_states:
            inactive.update(self.outgoing_index.get(sid, ()))
        return inactive

    def is_inactive_transition(self, transition_id: str) -> bool:
        return transition_id in self.inactive_transition_ids()

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
