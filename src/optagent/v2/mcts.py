"""§8 MCTS — cost-aware UCB for stochastic environments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from optagent.v2.state import Action, State
from optagent.v2.policy import Proposer


@dataclass
class MCTSNode:
    """Node in the MCTS tree."""
    state: State
    parent: Optional["MCTSNode"] = None
    children: Dict[str, "MCTSNode"] = field(default_factory=dict)
    visit_count: int = 0
    value_sum: float = 0.0
    pareto_values: List[List[float]] = field(default_factory=list)
    action: Optional[Action] = None

    def is_terminal(self) -> bool:
        return len(self.children) == 0 and self.visit_count > 0

    def ucb(self, parent_visit: int, c: float = 1.414) -> float:
        if self.visit_count == 0:
            return float('inf')
        exploitation = self.value_sum / self.visit_count
        exploration = c * (parent_visit ** 0.5) / (1 + self.visit_count)
        return exploitation + exploration


class MCTSOptimizer:
    """Monte Carlo Tree Search for optimization."""

    def __init__(self, value_predictor=None):
        self.value_predictor = value_predictor

    def search(self, state: State, proposer: Proposer, n_simulations: int, budget=None) -> Optional[Action]:
        root = MCTSNode(state=state)

        for _ in range(n_simulations):
            # Selection: UCB down to leaf
            node = self._select(root)

            # Expansion: proposer generates actions
            if not node.is_terminal():
                actions = proposer.generate_actions(node.state, n=5, temperature=0.7)
                for action in actions:
                    action_key = str(action)
                    if action_key not in node.children:
                        self._expand(node, action)

            # Simulation: lightweight value prediction
            value = self._simulate(node)

            # Backpropagation
            self._backpropagate(node, value)

        return self._best_action(root)

    def _select(self, node: MCTSNode) -> MCTSNode:
        """Select node with highest UCB until reaching a leaf."""
        while node.children and all(child.visit_count > 0 for child in node.children.values()):
            node = max(node.children.values(), key=lambda c: c.ucb(node.visit_count))
        return node

    def _expand(self, parent: MCTSNode, action: Action) -> MCTSNode:
        """Create child node for the given action."""
        child = MCTSNode(state=parent.state, parent=parent, action=action)
        parent.children[str(action)] = child
        return child

    def _simulate(self, node: MCTSNode) -> float:
        """Simulate a rollout from this node."""
        if self.value_predictor and node.action:
            return self.value_predictor.predict(node.action, node.state)
        return 0.5  # Default neutral value

    def _backpropagate(self, node: MCTSNode, value: float) -> None:
        """Backpropagate value up the tree."""
        while node is not None:
            node.visit_count += 1
            node.value_sum += value
            node = node.parent

    def _best_action(self, root: MCTSNode) -> Optional[Action]:
        """Select action with highest visit count."""
        if not root.children:
            return None
        return max(root.children.values(), key=lambda c: c.visit_count).action
