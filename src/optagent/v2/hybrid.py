"""§10 Plan⟷Policy Hybrid — two-tier architecture."""

from __future__ import annotations

from typing import Optional, Callable

from optagent.v2.state import Action, Observation, State, Transition
from optagent.v2.planner import Plan, Planner
from optagent.v2.mcts import MCTSOptimizer
from optagent.v2.reward import RewardSpec


class HybridOptimizer:
    """Planner generates coarse trajectory; MCTS refines local decisions."""

    def __init__(self, planner: Planner, mcts: MCTSOptimizer, executor: Optional[Callable] = None):
        self.planner = planner
        self.mcts = mcts
        self.executor = executor

    def optimize(self, state: State, reward_spec: RewardSpec, max_steps: int = 10) -> State:
        # Generate coarse plan
        plan = self.planner.create_plan(state, reward_spec, horizon=5)

        for step in range(max_steps):
            if plan.is_complete():
                break

            # MCTS refines next step
            action = self.mcts.search(
                state,
                proposer=self.planner.proposer,
                n_simulations=20,
            )

            if action is None:
                break

            # Execute
            observation = self._execute(action)

            # Update planner and state
            plan = self.planner.update(state, plan, observation)
            state = self._advance(state, action, observation)

        return state

    def _execute(self, action: Action) -> Observation:
        if self.executor:
            return self.executor(action)
        return Observation(action_id=str(action))

    def _advance(self, state: State, action: Action, observation: Observation) -> State:
        from optagent.v2.state import Transition
        transition = Transition(
            action=action,
            observation=observation,
            reward_contribution=observation.metrics,
            cost=action.cost(state),
        )
        state.trajectory.append(transition)
        return state
