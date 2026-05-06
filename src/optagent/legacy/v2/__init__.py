"""v2 domain-agnostic optimization framework (§0-§15).

Swap points (§0-§4):
  - State (state.py): Artifact, ArtifactSet, State, Transition, Knowledge, Observation
  - Action (action.py): Action protocol, ApplyHypothesis, RunEvaluation
  - Reward (reward.py): Objective, Constraint, RewardSpec, Aggregator, RewardEvaluation

Algorithmic layer (§5-§10):
  - Planner (planner.py): Plan, PlannedStep, DefaultPlanner
  - Rollout (rollout.py): RolloutBudget, RolloutResult, RolloutSimulator
  - Policy (policy.py): Proposer, LLMProposer
  - MCTS (mcts.py): MCTSNode, MCTSOptimizer
  - Value Predictor (value.py): ValueFeatures, ValuePredictor
  - Hybrid (hybrid.py): HybridOptimizer

Bridge (§15):
  - v1.5 compatibility (bridge.py): state_v1_to_v2, state_v2_to_v1
"""

from optagent.legacy.v2.state import (
    State,
    ArtifactSet,
    Artifact,
    Transition,
    Knowledge,
    Observation,
)

from optagent.legacy.v2.action import (
    Action,
    ApplyHypothesis,
    RunEvaluation,
    CostModel,
)

from optagent.legacy.v2.reward import (
    RewardSpec,
    RewardEvaluation,
    Objective,
    Constraint,
    CostModel as RewardCostModel,
    Aggregator,
    WeightedSum,
    Lexicographic,
    Tchebycheff,
    ExpectedHypervolumeImprovement,
    ConstrainedScalar,
)

from optagent.legacy.v2.planner import (
    Plan,
    PlannedStep,
    Planner,
    DefaultPlanner,
)

from optagent.legacy.v2.rollout import (
    RolloutBudget,
    RolloutResult,
    FuturePath,
    RolloutSimulator,
)

from optagent.legacy.v2.policy import (
    Proposer,
    LLMProposer,
)

from optagent.legacy.v2.mcts import (
    MCTSNode,
    MCTSOptimizer,
)

from optagent.legacy.v2.value import (
    ValueFeatures,
    ValuePredictor,
)

from optagent.legacy.v2.hybrid import (
    HybridOptimizer,
)

from optagent.legacy.v2.bridge import (
    state_v1_to_v2,
    state_v2_to_v1,
)

__version__ = "2.0.0-alpha"

__all__ = [
    # State layer
    "State",
    "ArtifactSet",
    "Artifact",
    "Transition",
    "Knowledge",
    "Observation",
    # Action layer
    "Action",
    "ApplyHypothesis",
    "RunEvaluation",
    "CostModel",
    # Reward layer
    "RewardSpec",
    "RewardEvaluation",
    "Objective",
    "Constraint",
    "RewardCostModel",
    "Aggregator",
    "WeightedSum",
    "Lexicographic",
    "Tchebycheff",
    "ExpectedHypervolumeImprovement",
    "ConstrainedScalar",
    # Planner
    "Plan",
    "PlannedStep",
    "Planner",
    "DefaultPlanner",
    # Rollout
    "RolloutBudget",
    "RolloutResult",
    "FuturePath",
    "RolloutSimulator",
    # Policy
    "Proposer",
    "LLMProposer",
    # MCTS
    "MCTSNode",
    "MCTSOptimizer",
    # Value
    "ValueFeatures",
    "ValuePredictor",
    # Hybrid
    "HybridOptimizer",
    # Bridge
    "state_v1_to_v2",
    "state_v2_to_v1",
]
