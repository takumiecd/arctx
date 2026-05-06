"""§10 Plan⟷Policy Hybrid — two-tier architecture.

Corresponds to PLANNING_AND_RL.md §10.
"""

from __future__ import annotations

from typing import Optional, Callable, Any

from optagent.legacy.v2.state import Observation, State
from optagent.legacy.v2.planner import Plan, Planner
from optagent.legacy.v2.mcts import MCTSOptimizer
from optagent.legacy.v2.reward import RewardSpec


class HybridOptimizer:
    """Planner generates coarse trajectory; MCTS refines local decisions (§10)."""

    def __init__(self, planner: Planner, mcts: MCTSOptimizer, executor: Optional[Callable] = None):
        self.planner = planner
        self.mcts = mcts
        self.executor = executor

    def optimize(self, state: State, reward_spec: RewardSpec, max_steps: int = 10) -> State:
        """Run plan-guided MCTS loop (§10.2)."""
        # Generate coarse plan
        plan = self.planner.create_plan(state, reward_spec, horizon=5)

        for step in range(max_steps):
            if plan.is_complete():
                break

            # Get current plan step
            plan_step = plan.steps[0] if plan.steps else None

            # Construct action filter and prior boost based on plan posture
            action_filter = self._make_action_filter(plan, plan_step)
            prior_boost = self._make_prior_boost(plan, plan_step)

            # MCTS refines action within plan constraints
            action = self.mcts.search(
                state,
                proposer=self.planner.proposer,
                n_simulations=20,
                action_filter=action_filter,
                prior_boost=prior_boost,
            )

            if action is None:
                break

            # Execute action
            observation = self._execute(action)

            # Transition state
            state = state.advance(action, observation, reward_spec=reward_spec)

            # Update plan (checks replan triggers §5.2)
            plan = self.planner.update(state, plan, observation)

        return state

    def _make_action_filter(self, plan: Plan, plan_step) -> Optional[Callable[[Any], bool]]:
        """Create action filter based on plan posture (§10.3).

        Returns:
          Callable[[Action], bool] or None based on posture:
          - "strict": only actions matching plan_step.action_subspace
          - "guided": no filter (boost via prior_boost instead)
          - "open": no filter, plan only sets budget/aggregator
        """
        if not plan_step or not plan_step.action_subspace:
            return None

        posture = plan.posture

        if posture == "strict":
            # Only allow actions matching subspace
            return plan_step.action_subspace
        else:  # "guided" or "open"
            # No filtering; any boost is handled via prior_boost
            return None

    def _make_prior_boost(self, plan: Plan, plan_step) -> Optional[Callable[[Any], float]]:
        """Create prior boost function based on plan posture (§10.3).

        Returns:
          Callable[[Action], float] that returns a boost multiplier for matching actions.
          - "strict": no boost (filtering handles it)
          - "guided": boost matching actions by 2.0x
          - "open": no boost
        """
        if not plan_step or not plan_step.action_subspace:
            return None

        posture = plan.posture

        if posture == "guided":
            # Return a boost function that gives 2.0x to matching actions
            def boost(action):
                if plan_step.action_subspace(action):
                    return 2.0
                else:
                    return 1.0
            return boost
        else:
            # "strict" or "open": no prior boost
            return None

    def _execute(self, action: Any) -> Observation:
        """Execute action and return observation."""
        if self.executor:
            return self.executor(action)
        return Observation(action_id=str(action))
