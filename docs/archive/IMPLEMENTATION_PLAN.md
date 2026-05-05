# Implementation Plan — Planning & RL Integration

## Overview

This document defines the phased implementation of the PLANNING_AND_RL.md v2 framework into the optagent codebase.

**Current state**: optagent has a working v1.5 implementation (`OptimizerState` with R/H/C + `ManagerAgent` with fixed workflow).  
**Target state**: v2 domain-agnostic framework with State/Action/Reward swap points, Planner, Rollout, MCTS, and Plan⟷Policy hybrid.

**Migration strategy**: non-destructive. New v2 modules live alongside v1.5; a compatibility layer bridges them. Old code is deprecated and removed only after v2 is fully functional.

---

## Phase 0 — Preparation

### Goals
- Establish testing and type-checking baseline
- Ensure existing tests pass
- Define module structure for v2

### Tasks
1. **Run existing tests**
   ```bash
   python -m pytest tests/ -v
   ```
   Fix any failures before touching code.

2. **Add mypy type checking** (optional but recommended)
   ```bash
   pip install mypy
   mypy src/optagent/ --ignore-missing-imports
   ```

3. **Create v2 module structure**
   ```
   src/optagent/v2/
   ├── __init__.py
   ├── state.py          # §2 State, ArtifactSet, Trajectory, Knowledge
   ├── action.py         # §3 Action Protocol, domain-specific kinds
   ├── reward.py         # §4 RewardSpec, Objective, Constraint, Aggregator
   ├── planner.py        # §5 Planner, Plan, PlannedStep, AdaptivePlanner
   ├── rollout.py        # §6 RolloutSimulator, RolloutBudget
   ├── policy.py         # §7 Proposer, LLM calibration strategies
   ├── mcts.py           # §8 MCTSOptimizer, cost-aware UCB, Pareto-MCTS
   ├── value.py          # §9 ValuePredictor
   ├── hybrid.py         # §10 Plan⟷Policy hybrid
   └── bridge.py         # Compatibility layer: v1.5 ↔ v2
   ```

### Acceptance Criteria
- All existing tests pass
- `src/optagent/v2/` directory exists with `__init__.py`
- CI (if any) is green

---

## Phase 1 — State / Action / Reward Swap Points

### Goals
- Implement the three pluggable interfaces from §2–§4
- Add compatibility bridge from v1.5 `OptimizerState`

### Tasks

#### 1.1 State Schema (`v2/state.py`)

Implement §2 dataclasses:

```python
@dataclass
class State:
    requirement: Requirement
    artifact: ArtifactSet
    trajectory: List[Transition]
    knowledge: Knowledge
```

Plus nested classes:
- `ArtifactSet` (candidates, pareto_front, incumbent)
- `Transition` (action, observation, reward_contribution, cost)
- `Knowledge` (ruled_out_regions, calibration, invariants, surrogate_models)

**Key decision**: `Requirement` can reuse the existing `Requirements` dataclass from `state_model.py` (it's already frozen and generic enough).

#### 1.2 Action Protocol (`v2/action.py`)

```python
class Action(Protocol):
    def apply(self, state: State) -> ArtifactCandidate: ...
    def cost(self, state: State) -> Cost: ...
    def observability(self) -> ObservationSchema: ...
```

Plus concrete kinds for hypothesis-test domain (the only domain we have today):
- `ApplyHypothesis(hypothesis)`
- `RunEvaluation(artifact)`

#### 1.3 Reward Spec (`v2/reward.py`)

```python
@dataclass
class RewardSpec:
    objectives: List[Objective]
    constraints: List[Constraint]
    aggregator: Aggregator
    cost_model: CostModel
```

Plus:
- `Objective` (name, direction, normalizer, reference)
- `Constraint` (predicate, kind, penalty)
- Aggregator implementations: `WeightedSum`, `Tchebycheff`, `Lexicographic`
- `CostModel`

**Key decision**: Default to `Lexicographic` with correctness as hard constraint, then improvement — this matches current `PromotionGate` behavior.

#### 1.4 Bridge (`v2/bridge.py`)

Convert v1.5 `OptimizerState` → v2 `State`:

```python
def state_v1_to_v2(optimizer_state: OptimizerState) -> State:
    """Convert v1.5 OptimizerState to v2 State."""
    # artifact: wrap existing artifacts into ArtifactSet
    # trajectory: build from hypotheses + evidence sequence
    # knowledge: initially empty (no learning history yet)
```

And reverse:

```python
def state_v2_to_v1(state: State) -> OptimizerState:
    """Convert v2 State back to v1.5 for legacy consumers."""
```

### Acceptance Criteria
- `State`, `Action`, `RewardSpec` can be instantiated
- Bridge round-trips without data loss (test)
- Existing `ManagerAgent` still works (unchanged)

---

## Phase 2 — Planner

### Goals
- Implement §5 Plan, PlannedStep, Planner Protocol
- Add replanning triggers
- Integrate with `ManagerAgent` as optional component

### Tasks

#### 2.1 Plan Data Structures (`v2/planner.py`)

```python
@dataclass
class PlannedStep:
    action: Action
    expected_observation: Observation
    expected_state_delta: StateDelta
    checkpoint: CheckpointSpec

@dataclass
class Plan:
    steps: List[PlannedStep]
    expected_terminal_state: State
    confidence: float
    assumptions: List[Invariant]
    fallbacks: List["Plan"]
```

#### 2.2 Planner Protocol

```python
class Planner(Protocol):
    def create_plan(self, state: State, reward_spec: RewardSpec, horizon: int) -> Plan: ...
    def step(self, state: State, plan: Plan) -> Tuple[Action, Plan]: ...
    def update(self, state: State, plan: Plan, observation: Observation) -> Plan: ...
```

#### 2.3 DefaultPlanner

A simple implementation that:
1. Generates N actions via proposer
2. Selects top-K by value predictor (Phase 4)
3. Chains them into a linear plan
4. Sets deviation threshold from calibration data

#### 2.4 Replanning Triggers

Implement §5.2 triggers:
- Deviation: `dist(observed, expected) > θ_dev`
- Assumption violation
- Budget exhausted
- Better path discovered (from rollout)
- Knowledge update

#### 2.5 Integration Point

Modify `ManagerAgent.optimize()` to accept optional `planner: Planner`:

```python
def optimize(self, requirements: Requirements, planner: Planner | None = None):
    if planner is None:
        # Legacy path: fixed workflow
        return self._legacy_optimize(requirements)
    
    # New path: planner-driven
    state = self._initialize_state(requirements)
    plan = planner.create_plan(state, reward_spec, horizon=3)
    
    while not plan.is_complete():
        action, plan = planner.step(state, plan)
        observation = self._execute_action(action)
        plan = planner.update(state, plan, observation)
        state = self._advance_state(state, action, observation)
```

### Acceptance Criteria
- `DefaultPlanner` produces a valid Plan
- Replanning triggers fire correctly (test with mocked observations)
- `ManagerAgent` works with and without planner

---

## Phase 3 — Rollout

### Goals
- Implement §6 RolloutSimulator
- Budget-aware path expansion
- Value pruning integration

### Tasks

#### 3.1 Rollout Budget (`v2/rollout.py`)

```python
@dataclass
class RolloutBudget:
    max_total_cost: Cost
    max_depth: int
    max_branching_per_node: int
    pruning: PruningPolicy
```

#### 3.2 RolloutSimulator

```python
class RolloutSimulator:
    def simulate(self, state: State, action: Action, depth: int, budget: RolloutBudget) -> RolloutResult:
        """Expand future paths from (state, action)."""
```

Features:
- Cost-bounded expansion (stop when budget exhausted)
- Knowledge-pruned (skip ruled-out regions)
- Value-pruned (skip below-threshold paths — requires Phase 4)

#### 3.3 RolloutResult

```python
@dataclass
class RolloutResult:
    paths: List[FuturePath]
    best_path: FuturePath
    expected_value: float
    expected_cost: Cost
    confidence: float
```

#### 3.4 Planner Integration

Add rollout to `DefaultPlanner.create_plan()`:
- After generating candidate actions, run lightweight rollout for each
- Use rollout result to rank actions before including in plan

### Acceptance Criteria
- Rollout explores paths within budget
- Knowledge-pruning skips ruled-out actions (test)
- Rollout result has `confidence` proportional to exploration ratio

---

## Phase 4 — Proposer Calibration

### Goals
- Implement §7 LLM calibration strategies
- Make LLM output usable as stochastic policy π(a|s)

### Tasks

#### 4.1 Proposer Interface (`v2/policy.py`)

```python
class Proposer(Protocol):
    def generate_actions(self, state: State, n: int, temperature: float) -> List[Action]: ...
    def score_actions(self, state: State, actions: List[Action]) -> List[float]: ...
```

#### 4.2 Calibration Strategies

Implement §7.2 strategies:
- **N-sample empirical**: sample N actions, use frequency as π̂(a)
- **Logprob-weighted**: use token-level logprobs (if available)
- **Self-consistency**: cluster semantically-equivalent actions

Default: N-sample empirical with N=5–20, chosen by cost budget.

#### 4.3 LLMProposer

Wrap existing backend (`OpenCodeBackend`, `ClaudeBackend`) as Proposer:

```python
class LLMProposer:
    def __init__(self, backend, calibration_strategy="n_sample"):
        self.backend = backend
        self.strategy = calibration_strategy
    
    def generate_actions(self, state, n, temperature):
        # Call backend n times with given temperature
        # Return list of parsed actions
```

#### 4.4 Integration with Planner

Replace direct backend calls in planner with Proposer:

```python
class DefaultPlanner:
    def __init__(self, proposer: Proposer, ...):
        self.proposer = proposer
    
    def create_plan(self, state, reward_spec, horizon):
        actions = self.proposer.generate_actions(state, n=10, temperature=0.7)
        # Score and rank
        ...
```

### Acceptance Criteria
- `LLMProposer` generates N distinct actions
- Calibration produces probability distribution (sums to ~1)
- Actions are semantically distinct (not just paraphrases)

---

## Phase 5 — MCTS

### Goals
- Implement §8 MCTSOptimizer
- Cost-aware UCB for stochastic environments
- Pareto-MCTS for multi-objective

### Tasks

#### 5.1 MCTS Node (`v2/mcts.py`)

```python
@dataclass
class MCTSNode:
    state: State
    parent: MCTSNode | None
    children: Dict[Action, MCTSNode]
    visit_count: int
    value_sum: float  # For scalarized values
    pareto_values: List[List[float]]  # For Pareto-MCTS
    action: Action | None  # Action taken to reach this node
```

#### 5.2 Cost-Aware UCB

```python
def ucb_cost_aware(node: MCTSNode, parent: MCTSNode, c: float, cost_model: CostModel) -> float:
    """UCB1 variant that accounts for action cost."""
    # Standard UCB + cost penalty
```

#### 5.3 MCTS Loop

```python
class MCTSOptimizer:
    def search(self, state: State, proposer: Proposer, n_simulations: int, budget: RolloutBudget) -> Action:
        root = MCTSNode(state=state)
        for _ in range(n_simulations):
            # Selection: UCB down to leaf
            node = self._select(root)
            
            # Expansion: proposer generates actions
            if not node.is_terminal():
                actions = proposer.generate_actions(node.state, n=5)
                for action in actions:
                    self._expand(node, action)
            
            # Simulation: lightweight value prediction
            value = self._simulate(node)
            
            # Backpropagation
            self._backpropagate(node, value)
        
        return self._best_action(root)
```

#### 5.4 Pareto-MCTS

For multi-objective problems:
- Track `pareto_values` at each node
- Selection uses hypervolume contribution instead of scalar UCB
- Backpropagation updates Pareto front

#### 5.5 Integration with Planner

MCTS can be used in two modes:
1. **Standalone**: MCTS directly selects actions (no plan)
2. **Plan refinement**: MCTS refines a coarse plan into concrete actions

Start with mode 1; mode 2 comes in Phase 6.

### Acceptance Criteria
- MCTS completes N simulations without error
- Cost-aware UCB prefers cheaper actions when values are similar (test)
- Pareto-MCTS tracks non-dominated front

---

## Phase 6 — Plan⟷Policy Hybrid

### Goals
- Implement §10 two-tier architecture
- Planner generates coarse trajectory; MCTS refines local decisions

### Tasks

#### 6.1 Hybrid Architecture (`v2/hybrid.py`)

```python
class HybridOptimizer:
    def __init__(self, planner: Planner, mcts: MCTSOptimizer):
        self.planner = planner  # Coarse trajectory
        self.mcts = mcts        # Local action selection
    
    def optimize(self, state: State, reward_spec: RewardSpec) -> State:
        # Generate coarse plan
        plan = self.planner.create_plan(state, reward_spec, horizon=5)
        
        while not plan.is_complete():
            # MCTS refines next step
            action = self.mcts.search(
                state,
                proposer=self.planner.proposer,
                n_simulations=20,
                budget=RolloutBudget(max_total_cost=...),
            )
            
            # Execute
            observation = self._execute(action)
            
            # Update both planner and MCTS state
            plan = self.planner.update(state, plan, observation)
            state = self._advance(state, action, observation)
        
        return state
```

#### 6.2 Commitment Levels

Implement §10.3 commitment levels:
- `full_commit`: planner's chosen path (no MCTS)
- `branch_commit`: MCTS explores within planner's subtree
- `local_search`: MCTS free to deviate
- `deviation_threshold`: switch to `local_search` when observed deviates from expected

#### 6.3 Integration Test

End-to-end test with mock backend:
1. Initialize state
2. Run hybrid optimizer
3. Verify planner and MCTS both contributed
4. Check state trajectory is valid

### Acceptance Criteria
- Hybrid optimizer completes a full optimization run
- Planner generates coarse plan; MCTS selects concrete actions
- Commitment level switches appropriately based on deviation

---

## Phase 7 — Migration & Cleanup

### Goals
- Migrate existing domains to v2
- Remove v1.5 code
- Update documentation

### Tasks

#### 7.1 Domain Migration

Migrate `KernelOptimizationStrategy` to v2:
- Implement `KernelState` (extends `State`)
- Implement `KernelAction` kinds (`ApplyHypothesis`, `RunEvaluation`)
- Define `KernelRewardSpec` (latency, correctness, eligibility)
- Plug into v2 framework

#### 7.2 ManagerAgent Refactor

Replace `ManagerAgent` internals to use v2:
- `optimize()` becomes thin wrapper around `HybridOptimizer`
- Legacy `_legacy_optimize()` path removed
- File-based protocol preserved (child agents still work)

#### 7.3 Remove v1.5 Code

Delete:
- `core/models.py` (old OptimizationState)
- `core/state.py` (old persistence)
- Keep `core/state_model.py` until v2 fully replaces it

#### 7.4 Update Documentation

- Update `ARCHITECTURE.md` to describe v2
- Update `README.md` with v2 quickstart
- Move `PLANNING_AND_RL.md` to top-level or link prominently

### Acceptance Criteria
- All tests pass with v2 only
- No imports from v1.5 modules
- Documentation reflects v2 architecture

---

## Appendix A — Testing Strategy

### Unit Tests (per phase)
- State/Action/Reward: instantiation, serialization, bridge round-trip
- Planner: plan creation, trigger detection, replanning
- Rollout: budget enforcement, pruning, confidence
- MCTS: UCB correctness, backpropagation, Pareto front
- Hybrid: end-to-end with mock backend

### Integration Tests
- Full optimization run with `MockBackend`
- Bridge: v1.5 state → v2 → v1.5
- Performance: MCTS should find better actions than greedy baseline

### Regression Tests
- Existing `ManagerAgent` tests must pass until Phase 7
- `test_state_model.py` preserved until migration complete

---

## Appendix B — Risk Mitigation

| Risk | Mitigation |
|---|---|
| v2 over-engineered | Start simple; each phase has minimal viable scope |
| LLM API costs explode | CostModel + budget enforcement from Phase 3 |
| Migration breaks existing workflows | Bridge layer + dual-path until Phase 7 |
| MCTS too slow | Lightweight value predictor (Phase 4) + parallel simulation |
| Multi-objective too complex | Default to single-objective; Pareto is optional |

---

## Appendix C — Timeline Estimate

| Phase | Scope | Est. Time |
|---|---|---|
| 0 | Prep | 1 day |
| 1 | State/Action/Reward | 2–3 days |
| 2 | Planner | 2 days |
| 3 | Rollout | 2 days |
| 4 | Proposer Calibration | 2 days |
| 5 | MCTS | 3–4 days |
| 6 | Hybrid | 2 days |
| 7 | Migration | 2–3 days |
| **Total** | | **16–19 days** |

This assumes focused work. Parallelizable: Phase 3+4 can overlap; Phase 5+6 partially overlap.

---

*Last updated: 2026-05-05*
