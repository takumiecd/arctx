"""§8 MCTS — cost-aware UCB for stochastic environments.

Corresponds to PLANNING_AND_RL.md §8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

from optagent.legacy.v2.state import State, Artifact, Observation
from optagent.legacy.v2.policy import Proposer
from optagent.legacy.v2.pareto import pareto_merge
from optagent.legacy.v2.reward import Objective


@dataclass
class MCTSNode:
    """Node in the MCTS tree (§8.2)."""
    state: State
    parent: Optional["MCTSNode"] = None
    children: Dict[str, "MCTSNode"] = field(default_factory=dict)
    visit_count: int = 0
    value_sum: float = 0.0
    value_samples: List[float] = field(default_factory=list)  # For stochastic backprop
    pareto_front: List[Artifact] = field(default_factory=list)  # Per-subtree Pareto artifacts
    action: Optional[Any] = None
    prior: float = 0.0  # Prior probability from proposer
    depth: int = 0  # Depth from root (for termination via max_depth)
    expanded: bool = False  # Whether this node has been expanded (proposer called once)
    is_terminal: bool = False  # Explicitly marked as terminal (max depth or no actions)

    def ucb(self, parent_visit: int, c: float = 1.414) -> float:
        """Cost-aware UCB1 (§8.3): Q(a)/cost(a) + c·√(ln N / n_a)"""
        if self.visit_count == 0:
            return float('inf')

        exploitation = self.value_sum / self.visit_count
        exploration = c * ((parent_visit ** 0.5) / self.visit_count)

        # Cost-aware adjustment applied in _select, not here
        return exploitation + exploration


class MCTSOptimizer:
    """Monte Carlo Tree Search for optimization (§8)."""

    def __init__(self, value_predictor=None, aggregator=None, objectives: List[Objective] = None):
        self.value_predictor = value_predictor
        self.aggregator = aggregator  # For backprop scalarization (§8.4)
        self.objectives = objectives or []  # For Pareto domination checks

    def search(
        self,
        state: State,
        proposer: Proposer,
        n_simulations: int,
        budget=None,
        action_filter: Optional[Callable] = None,
        max_depth: int = 10,
        prior_boost: Optional[Callable[[Any], float]] = None,
        return_tree: bool = False,
    ) -> Optional[Any]:
        """MCTS search with optional action filtering (§10.2 plan coupling).

        Args:
            state: Root state
            proposer: Generates candidate actions
            n_simulations: Number of rollouts
            budget: Optional cost budget
            action_filter: Optional predicate(Action) -> bool for plan coupling
            max_depth: Maximum tree depth before termination
            prior_boost: Optional callable(Action) -> float for guided search
            return_tree: If True, return (best_action, root_node)

        Returns:
            Best action found, or (best_action, root_node) if return_tree=True,
            or None if no valid actions
        """
        root = MCTSNode(state=state, depth=0)

        for _ in range(n_simulations):
            # Selection: UCB descent to leaf
            node = self._select(root)

            # Expansion: proposer generates actions (only once per node)
            if not node.is_terminal and not node.expanded:
                actions = proposer.generate_actions(node.state, n=5, temperature=0.7)
                if action_filter:
                    actions = [a for a in actions if action_filter(a)]

                if actions:
                    # Score actions and apply prior boost if provided
                    priors = proposer.score_actions(node.state, actions)

                    if prior_boost:
                        # Apply boost to matching actions and renormalize
                        boosted_priors = []
                        for action, prior in zip(actions, priors):
                            boost = prior_boost(action)
                            boosted_priors.append(prior * boost)
                        # Renormalize
                        total = sum(boosted_priors)
                        if total > 0:
                            priors = [p / total for p in boosted_priors]

                    # Create children with stable action IDs
                    for action, prior in zip(actions, priors):
                        action_key = self._make_action_key(action)
                        if action_key not in node.children:
                            child = self._expand(node, action, prior, max_depth)
                else:
                    # No actions available; mark node as terminal
                    node.is_terminal = True

                node.expanded = True

            # Simulation: lightweight value prediction with synthetic observation
            value = self._simulate(node)

            # Backpropagation with Pareto tracking
            self._backpropagate(node, value)

        best_action = self._best_action(root)
        if return_tree:
            return best_action, root
        return best_action

    def _make_action_key(self, action: Any) -> str:
        """Generate stable key for action based on content, not generation order.

        Hash the action's (class_name, content) to ensure deterministic identity.
        """
        from hashlib import md5
        action_class = action.__class__.__name__
        action_repr = repr(sorted(vars(action).items()))
        hash_key = md5(f"{action_class}:{action_repr}".encode()).hexdigest()
        return hash_key

    def _select(self, node: MCTSNode) -> MCTSNode:
        """Select node with highest cost-aware UCB until reaching a leaf (§8.3).

        Descend while:
        1. Node has children, AND
        2. Either not all children are visited (exploration bonus for unvisited), OR
        3. All children visited and we pick the best UCB child (exploitation).

        Stop at terminal nodes or when no valid children exist.
        """
        while node.children and not node.is_terminal:
            # Standard MCTS: unvisited nodes have UCB = +inf, always selected first
            # Cost-aware UCB: Q(a)/cost(a) + c·√(ln N / n_a)
            def cost_aware_ucb(child):
                cost = child.action.cost(node.state) if child.action else 1.0
                cost = max(cost, 1e-6)  # Avoid divide-by-zero
                base_ucb = child.ucb(node.visit_count)
                return base_ucb / cost

            node = max(node.children.values(), key=cost_aware_ucb)

        return node

    def _expand(self, parent: MCTSNode, action: Any, prior: float = 0.0, max_depth: int = 10) -> MCTSNode:
        """Create child node by applying action to parent state (§1, §2)."""
        # Synthesize observation using value predictor
        synthetic_obs = self._synthesize_observation(action, parent.state)

        # Transition to new state
        child_state = parent.state.advance(action, synthetic_obs)

        # Create child with depth tracking
        child = MCTSNode(
            state=child_state,
            parent=parent,
            action=action,
            prior=prior,
            depth=parent.depth + 1,
        )

        # Mark as terminal if max depth reached
        if child.depth >= max_depth:
            child.is_terminal = True

        # Mark transition as synthetic
        if child_state.trajectory:
            child_state.trajectory[-1].metadata = {"synthetic": True}

        parent.children[self._make_action_key(action)] = child
        return child

    def _synthesize_observation(self, action: Any, state: State) -> Observation:
        """Synthesize predicted observation using value predictor."""
        if self.value_predictor:
            predicted_value = self.value_predictor.predict(action, state)
        else:
            predicted_value = 0.5

        # Create synthetic observation with predicted metrics
        return Observation(
            action_id=str(action),
            metrics={"predicted_value": predicted_value},
            metadata={"synthetic": True},
        )

    def _simulate(self, node: MCTSNode) -> float:
        """Simulate value at this node (lightweight prediction)."""
        if self.value_predictor:
            # Use current state's incumbent as baseline if available
            if node.state.artifact.incumbent:
                return self.value_predictor.predict(node.action, node.state) if node.action else 0.5
            return 0.5
        return 0.5

    def _backpropagate(self, node: MCTSNode, value: float) -> None:
        """Backpropagate value up tree with Pareto front merging (§8.2, §8.4)."""
        while node is not None:
            node.visit_count += 1
            node.value_sum += value
            node.value_samples.append(value)

            # Merge Pareto front from children into parent
            # Use proper domination-aware merging
            if node.state.artifact.candidates:
                for artifact in node.state.artifact.candidates:
                    if self.objectives:
                        # Use proper Pareto merge with domination checks
                        node.pareto_front = pareto_merge(
                            node.pareto_front,
                            artifact,
                            self.objectives
                        )
                    else:
                        # No objectives defined, just append if not present
                        if artifact not in node.pareto_front:
                            node.pareto_front.append(artifact)

            node = node.parent

    def _best_action(self, root: MCTSNode) -> Optional[Any]:
        """Select action with highest visit count (exploitation)."""
        if not root.children:
            return None
        best_child = max(root.children.values(), key=lambda c: c.visit_count)
        return best_child.action
