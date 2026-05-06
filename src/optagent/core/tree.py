"""Depth-oriented prediction and evidence trees."""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.schema import ActionSpec, StateNode, TransitionRecord


@dataclass(frozen=True)
class PlannedTransition:
    """Predicted edge in a PredictionTree."""

    from_state_id: str
    to_predicted_state_id: str
    action_spec: ActionSpec
    assumptions: tuple[str, ...] = ()
    confidence: float | None = None


@dataclass
class PredictionTree:
    """Future state tree grouped by depth."""

    nodes_by_depth: dict[int, list[StateNode]] = field(default_factory=dict)
    planned_transitions: dict[str, PlannedTransition] = field(default_factory=dict)

    def add_node(self, node: StateNode) -> None:
        self.nodes_by_depth.setdefault(node.depth, []).append(node)

    def add_transition(self, transition_id: str, transition: PlannedTransition) -> None:
        self.planned_transitions[transition_id] = transition

    def depth(self, depth: int) -> list[StateNode]:
        return list(self.nodes_by_depth.get(depth, ()))


@dataclass
class EvidenceTree:
    """Observed transition tree grouped by depth."""

    nodes_by_depth: dict[int, list[StateNode]] = field(default_factory=dict)
    transitions: dict[str, TransitionRecord] = field(default_factory=dict)

    def add_node(self, node: StateNode) -> None:
        self.nodes_by_depth.setdefault(node.depth, []).append(node)

    def append_transition(self, transition: TransitionRecord) -> None:
        self.transitions[transition.transition_id] = transition

    def depth(self, depth: int) -> list[StateNode]:
        return list(self.nodes_by_depth.get(depth, ()))
