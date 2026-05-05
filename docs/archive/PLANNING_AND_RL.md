# Planning and Reinforcement Learning Integration

## Overview

This document defines a **domain-agnostic framework** for integrating planning, state prediction, and reinforcement learning (RL) into the optagent system.

The framework is organized around **three swap points** — State, Action, Reward — that instantiate the framework for any optimization domain (hypothesis testing, hyperparameter search, iterative refinement, compositional assembly). The algorithmic layer (planner, rollout, policy, MCTS) is then defined once, on top of these swap points.

**Core framing**: optimization is **state transition prediction** — analogous to next-token prediction in LLMs, but at the level of optimization states. A planner predicts the next optimal state; a policy proposes actions; a value predictor estimates outcomes; MCTS reconciles exploration and exploitation under cost.

This is v2. v1 was scoped to a hypothesis-test workflow (`X = (R, H, C)`) and a single-objective scalar reward; both assumptions are lifted here.

---

# Part I — Formalism

## §0. Design Dimensions

The framework has **three pluggable interfaces**. All algorithmic content (Part II) is written against these interfaces, not against a specific domain.

| Dimension | What it defines | Domain-specific? |
|---|---|---|
| **State** (§2) | What the agent knows: artifact, history, learned constraints | Yes — schema differs per domain |
| **Action** (§3) | How the agent transforms state, with cost and observability | Yes — proposer differs per domain |
| **Reward** (§4) | How outcomes are scored: objectives, constraints, aggregator, cost | Yes — objectives differ per domain |

**Algorithmic layer (Part II)** — planner, rollout, policy, MCTS, value predictor, plan/policy hybrid — is defined **once** against the abstract State/Action/Reward.

**Practice layer (Part III)** — domain instantiations, implementation phases — fills in the three dimensions for concrete domains.

This separation is the central organizing principle of v2.

---

## §1. Philosophy: Optimization as State Transition Prediction

### 1.1 Frame

```
X_t  ──[ a_t ]──>  X_{t+1}
```

Where `X_t` is an optimization state (§2), `a_t` is an action (§3), and the transition produces a new state plus an observation contributing to reward (§4).

The agent's central problem: **predict the optimal next state** given the current one. This subsumes:

- *Which action to take?* (policy)
- *What outcome to expect?* (value)
- *When to stop?* (termination)
- *When the prediction was wrong, what changed?* (replanning)

### 1.2 Analogy to LLM Next-Token Prediction

| LLM | Optimization Agent |
|-----|---------------------|
| Token sequence | State trajectory |
| `P(next_token \| context)` | `P(next_state \| state)` |
| Autoregressive generation | Sequential action selection |
| Training corpus | Optimization history |
| Sampling temperature | Exploration/exploitation balance |

The analogy is structural, not literal: states are not tokens, transitions are stochastic and costly, and the reward signal is delayed and multi-dimensional. Part II addresses each of these gaps.

### 1.3 Why This Frame

1. **Unifies disparate workflows** under one schema (Part III shows four).
2. **Makes RL applicable** without retraining the underlying LLM (§7, §8).
3. **Gives planning a precise meaning** — a plan is a predicted trajectory of state transitions (§5).

---

## §2. State Schema

### 2.1 Definition

```python
@dataclass
class State:
    requirement: Requirement       # Fixed goal specification
    artifact: ArtifactSet          # Current candidate solution(s) — possibly a Pareto front
    trajectory: List[Transition]   # Ordered (action, observation) history
    knowledge: Knowledge           # Learned constraints, ruled-out regions, calibration data
```

**Semantic separation** (this is the key correction to v1):

- `artifact` — *what we have now.* The starting point for the next action.
- `trajectory` — *how we got here.* Used for credit assignment and replay.
- `knowledge` — *what we learned.* Used to prune the search space and avoid redundant evaluation.

In v1, `H` (hypotheses) and `C` (evidence) collapsed these three. Two states with identical `H, C` but different intermediate artifacts were indistinguishable, even though their successor sets differ. v2 makes artifact a first-class element.

### 2.2 ArtifactSet

```python
@dataclass
class ArtifactSet:
    candidates: List[Artifact]              # All retained candidates
    pareto_front: List[Artifact]            # Non-dominated candidates (per §4 objectives)
    incumbent: Optional[Artifact]           # Current best by aggregator
```

Why a *set*, not a single artifact: multi-objective optimization (§4) typically yields a Pareto front. Even single-objective problems benefit from retaining several near-optimal candidates for downstream selection or ensembling.

### 2.3 Trajectory

```python
@dataclass
class Transition:
    action: Action
    observation: Observation
    reward_contribution: RewardSample
    cost: Cost
    timestamp: int
```

The trajectory is **action-agnostic** — it does not assume actions are "hypotheses" or "configs" or anything domain-specific. Domain-specific event types live in `action: Action` (§3).

### 2.4 Knowledge

```python
@dataclass
class Knowledge:
    ruled_out_regions: List[Region]         # Action subspaces known to fail/dominate
    calibration: CalibrationData            # Cost/reward predictor calibration
    invariants: List[Invariant]             # Learned constraints (e.g., "always violates SLO")
    surrogate_models: Dict[str, Surrogate]  # Per-objective surrogates, if any
```

Knowledge is **what makes the search efficient over time.** §9 (Value Predictor) reads from it; §6 (Rollout) prunes against it; §5 (Replanning) checks invariants.

### 2.5 Domain Projections

The same schema instantiates for different domains by populating fields differently:

| Domain | `artifact` | `trajectory` event | `knowledge` content |
|---|---|---|---|
| Hypothesis-test | Implemented variant + Pareto front | (Hypothesis, Evidence) | Failed hypothesis patterns |
| HPO | Config + Pareto front | (Config, Metric) | Excluded hyperparameter regions |
| Iterative refinement | Code state + edit history | (Edit, Test result) | Failing test patterns, regression suite |
| Compositional | Module DAG + variants | (Swap, Performance) | Incompatible module pairs |

§11 expands each.

---

## §3. Action Space

### 3.1 Action Protocol

```python
class Action(Protocol):
    def apply(self, state: State) -> ArtifactCandidate:
        """Produce a new candidate artifact (does not yet update knowledge)."""
        ...
    
    def cost(self, state: State) -> Cost:
        """Estimated cost of executing this action — wallclock, $, evaluation budget."""
        ...
    
    def observability(self) -> ObservationSchema:
        """Declares what will be observed after execution (objective measurements, side signals)."""
        ...
```

Actions are **first-class, domain-pluggable units of state transition.** v1 pre-committed to `propose / implement / evaluate` as workflow phases. v2 treats those as one possible *kind* of action; other domains use other kinds.

### 3.2 Domain-Specific Action Kinds

| Domain | Action examples |
|---|---|
| Hypothesis-test | `ApplyHypothesis(h)`, `RunEvaluation(artifact)` |
| HPO | `SetParameter(name, value)`, `SampleConfig(distribution)` |
| Iterative refinement | `EditArtifact(diff)`, `RunTests(artifact)` |
| Compositional | `SwapModule(slot, candidate)`, `BenchmarkComposition(graph)` |

The proposer (§7) is the component that **generates candidate actions** from a state. Different domains plug in different proposers; MCTS (§8) and rollout (§6) call the proposer abstractly.

### 3.3 Action Cost and Observability

`cost()` and `observability()` are **first-class** because they govern algorithmic behavior:

- Cost feeds the cost-aware UCB variant in §8 and the budget-bounded rollout in §6.
- Observability declares which objectives (§4) will be measured — a cheap proxy evaluation may report only one objective; a full evaluation reports all.

Without these, "MCTS over LLM-proposed actions" devolves into uniform exploration of a hugely uneven cost landscape.

---

## §4. Reward Spec

### 4.1 Decomposition

Reward is **not a scalar function**. It is a structured spec:

```python
@dataclass
class RewardSpec:
    objectives: List[Objective]      # Multi-objective vector r ∈ R^k
    constraints: List[Constraint]    # Hard (validity) and soft (preference) constraints
    aggregator: Aggregator           # Pluggable scalarization for use by RL backprop
    cost_model: CostModel            # Cost accounting for cost-aware reward
```

### 4.2 Objectives

```python
@dataclass
class Objective:
    name: str
    direction: Literal["minimize", "maximize"]
    normalizer: Callable[[float], float]   # Scale unification across objectives
    reference: Optional[float] = None      # Baseline for ratio/improvement framing
```

A single objective is the trivial case (`k = 1`). Multi-objective is the default abstraction; nothing breaks if `k = 1`.

### 4.3 Constraints

```python
@dataclass
class Constraint:
    predicate: Callable[[State, Observation], bool]
    kind: Literal["hard", "soft"]
    penalty: float = 0.0   # Used when kind == "soft"
```

- **Hard** constraints: violation makes the candidate inadmissible (e.g., correctness, validity).
- **Soft** constraints: violation incurs a penalty subtracted by the aggregator.

v1's `validity` and `applicability` are hard constraints under this schema, not multiplicative reward terms.

### 4.4 Aggregators

Aggregators reduce the objective vector to a scalar **at the point of use** (e.g., MCTS backprop). Different uses can pick different aggregators:

| Aggregator | When to use |
|---|---|
| `WeightedSum(w)` | Preferences are linear and known |
| `Tchebycheff(reference, weights)` | Want even coverage of the Pareto front |
| `ExpectedHypervolumeImprovement(front)` | Want to maximize Pareto-front quality |
| `Lexicographic(order)` | Strict objective priority (e.g., correctness ≫ speed) |
| `ConstrainedScalar(primary, others_as_constraints)` | One objective dominates; others become thresholds |

v1's `improvement × validity × applicability` is `WeightedSum(k=1)` plus hard constraints folded in as multipliers. v2 makes this an explicit choice rather than a baked-in assumption.

### 4.5 Cost-Aware Reward

```python
@dataclass
class CostModel:
    units: Literal["wallclock_s", "dollars", "evaluations"]
    accumulator: Callable[[List[Cost]], Cost]
```

The algorithmic layer can compute **reward per unit cost** (`r/c`) for cost-bounded search. This is essential when evaluations are minutes-to-hours expensive — selecting purely on raw reward burns the budget before exploring promising regions.

§6 (rollout) and §8 (MCTS) both use cost-aware variants.

### 4.6 Reward as a First-Class Object

The reward spec is **part of the agent's input**, not hardcoded. Different runs against the same codebase can carry different `RewardSpec` instances (e.g., latency-priority vs. memory-priority builds). The agent's algorithmic behavior is unchanged; only the spec varies.

---

# Part II — Algorithms

## §5. Planner & Replanning

### 5.1 Plan as Predicted Trajectory

```python
@dataclass
class PlannedStep:
    action: Action
    expected_observation: Observation
    expected_state_delta: StateDelta
    checkpoint: CheckpointSpec   # What to verify after this step
    
@dataclass
class Plan:
    steps: List[PlannedStep]
    expected_terminal_state: State
    confidence: float
    assumptions: List[Invariant]  # Preconditions tied to state.knowledge
    fallbacks: List["Plan"]       # Pre-computed alternatives
```

A plan is **a predicted trajectory through the state space** — exactly the prediction object the philosophy in §1 asks for.

### 5.2 Replanning Triggers (Explicit)

v1 said "plans are loose and adapt continuously." v2 replaces that with **named triggers**:

| Trigger | Condition | Action |
|---|---|---|
| **Deviation** | `dist(observed, expected) > θ_dev` | Replan from current state |
| **Assumption violation** | An `Invariant` in `assumptions` is contradicted | Drop subtree relying on assumption; replan |
| **Budget exhausted** | `Σ cost(steps_done) > budget` | Replan with reduced horizon or different aggregator |
| **Better path discovered** | Rollout (§6) surfaces a path with `EI > current_plan.expected_value` | Switch plans |
| **Knowledge update** | New ruled-out region intersects remaining steps | Prune and replan |

The threshold `θ_dev` is itself adaptive — set as a function of historical noise on this objective (read from `state.knowledge.calibration`).

### 5.3 Planner Interface

```python
class Planner(Protocol):
    def create_plan(self, state: State, reward_spec: RewardSpec, horizon: int) -> Plan: ...
    def step(self, state: State, plan: Plan) -> Tuple[Action, Plan]: ...
    def update(self, state: State, plan: Plan, observation: Observation) -> Plan: ...
```

`update` checks all triggers and returns either the unchanged plan or a replan. This is the **only** place where "loose adaptation" is operationalized.

---

## §6. Rollout: Horizon vs Branching

### 6.1 Why Rollout

Look-ahead from the current state to evaluate candidate actions before committing. The challenge: **cost**. A rollout of depth `d` and branching `b` evaluates `b^d` paths; even modest values explode.

### 6.2 Budget Allocation

```python
@dataclass
class RolloutBudget:
    max_total_cost: Cost
    max_depth: int
    max_branching_per_node: int
    pruning: PruningPolicy
```

Three knobs, one budget. v1 hardcoded `depth=3`; v2 makes the tradeoff explicit:

- **Cost-bounded**: stop expansion when `Σ cost > max_total_cost` regardless of depth.
- **Knowledge-pruned**: skip subtrees whose root action is in `state.knowledge.ruled_out_regions`.
- **Value-pruned**: skip subtrees whose value-predictor estimate (§9) is below a threshold.

### 6.3 Rollout Output

```python
@dataclass
class RolloutResult:
    paths: List[FuturePath]
    best_path: FuturePath
    expected_value: float
    expected_cost: Cost
    confidence: float    # Function of paths explored vs space size
```

Confidence matters: a high-value path discovered after exploring 1% of the budget is less trustworthy than the same path after 50%. The planner uses confidence to decide whether to replan based on the rollout (§5.2 trigger 4).

---

## §7. Policy: LLM as Stochastic Policy

### 7.1 The Calibration Problem

AlphaZero's policy network outputs a calibrated probability distribution `π(a | s)` over actions. **An LLM does not.** Naively treating the LLM's first sampled response as `π(a | s)` produces a degenerate point distribution with no exploration signal.

v1 said "use LLM as a fixed policy π" without addressing this. v2 makes the calibration strategy explicit.

### 7.2 Calibration Strategies

| Strategy | Mechanism | When to use |
|---|---|---|
| **N-sample empirical** | Sample N actions at temperature T; use frequency as `π̂(a)` | Default; robust |
| **Logprob-weighted** | Use token-level logprobs to score generated actions | When logprobs are available and reliable |
| **Self-consistency** | Sample N; cluster semantically-equivalent actions; weight by cluster size | Diverse phrasings of the same underlying action |
| **Tree-of-thought** | LLM proposes K branches, ranks them, prunes | When LLM can reliably self-evaluate |

The default is N-sample empirical with `N` chosen by cost budget — typically 5–20 per node.

### 7.3 LLM Roles

The LLM appears in three distinct roles, often conflated in v1:

| Role | What it does | Section |
|---|---|---|
| **Proposer** | Generate candidate actions for a state | §3, §6, §8 |
| **Policy** | Score / select among proposed actions | §7, §8 |
| **Evaluator** | Estimate value of a state without full execution | §9 |

A single LLM can play all three, but they are **separate calls with separate prompts.** Mixing them produces poorly-calibrated estimates because the model conflates "what to do" with "how good is this."

### 7.4 Policy Interface

```python
class Policy(Protocol):
    def propose_actions(self, state: State, n: int) -> List[Tuple[Action, float]]:
        """Return (action, prior_probability) pairs."""
        ...
    
    def evaluate_state(self, state: State) -> float:
        """Lightweight value estimate without execution."""
        ...
```

---

## §8. MCTS over Stochastic Environments

### 8.1 Departure from Vanilla MCTS

Standard MCTS assumes a deterministic, low-cost, fully-observable environment. **All three assumptions fail** in optimization:

| Assumption | Why it fails here | v2 response |
|---|---|---|
| Deterministic transitions | LLM-generated implementations are non-deterministic; evaluation noise | Stochastic node values; track variance |
| Low simulation cost | Full evaluation can take minutes-to-hours | Cost-aware UCB (§8.3) |
| Full observability | Single evaluation samples one corner of the input distribution | POMDP-style belief over true value |

### 8.2 Node Structure

```python
@dataclass
class MCTSNode:
    state: State
    visit_count: int
    value_samples: List[RewardSample]   # Stochastic backprop targets
    cost_accumulated: Cost
    pareto_front: List[Artifact]        # For Pareto-MCTS variant
    children: Dict[Action, "MCTSNode"]
    prior: Dict[Action, float]          # From policy.propose_actions
```

Each node carries the Pareto front of artifacts seen in its subtree. This enables Pareto-MCTS: a child is *not* dominated by a sibling if it contributes a non-dominated artifact, even with a lower aggregated reward.

### 8.3 Cost-Aware UCB

Standard UCB1: `UCB(a) = Q(a) + c · √(ln N / n_a)`

Cost-aware variant:

```
UCB_cost(a) = Q(a) / cost(a) + c · √(ln N / n_a)
```

Or, for already-explored nodes:

```
UCB_cost(a) = Q(a) + c · √(ln N / n_a) · √(median_cost / cost(a))
```

The latter penalizes exploration of expensive untested actions when cheap alternatives exist.

### 8.4 Aggregator Choice for Backprop

Backprop requires a scalar. Choose the aggregator (§4.4) per use:

- **Exploration phase**: Tchebycheff with random reference points → broad Pareto-front coverage.
- **Exploitation phase**: ExpectedHypervolumeImprovement → concentrate on front-improving actions.
- **Final selection**: Lexicographic on user-stated priorities.

These can change *within a single search* — early nodes use exploration aggregators, mature nodes use exploitation aggregators.

### 8.5 Credit Assignment

When a deep path produces a high-value terminal state, which action gets credit? v2 uses **cost-weighted backprop**:

```
credit(action_i) = (terminal_reward / depth) · (cost_i / total_path_cost)^(-α)
```

Cheap actions on a high-reward path get disproportionate credit (they were efficient choices). The exponent `α ∈ [0, 1]` tunes this; `α = 0` reduces to uniform credit, `α = 1` gives full inverse-cost weighting.

### 8.6 Search Loop

```python
def mcts_search(root: State, budget: SearchBudget) -> Action:
    while not budget.exhausted():
        node = select(root)                              # Cost-aware UCB descent
        actions = policy.propose_actions(node.state, n) # §7
        best_action = expand(node, actions)             # Pick by prior + value
        reward, cost = simulate(node, best_action)      # Real or value-predictor
        backprop(node, reward, cost)                    # §8.5
    return best_child(root, criterion=Lexicographic)
```

`simulate` is either a real action execution (expensive, accurate) or a value-predictor call (§9, cheap, approximate). The choice is itself part of the search budget.

---

## §9. Value Predictor

### 9.1 Why a Predictor

Full execution per candidate is too expensive. A lightweight predictor filters unpromising candidates before they consume budget.

### 9.2 Grounded Features

v1 listed vague features (`similarity_to_past_winners`, etc.). v2 grounds each in §2 and §4:

```python
@dataclass
class ValueFeatures:
    distance_to_pareto_winners: float        # § 2.4 knowledge.surrogate_models
    expected_hypervolume_gain: float         # § 4.4 EHVI computed against artifact.pareto_front
    constraint_violation_probability: float  # § 4.3 hard constraints + surrogate
    expected_cost: Cost                      # § 3.3 + cost-model surrogate
    novelty_score: float                     # Distance from trajectory action space
```

Each feature has a defined provenance; none are hand-wavy.

### 9.3 Predictor Variants

| Variant | Implementation | Trade-off |
|---|---|---|
| LLM-as-evaluator | Prompt: "rate this candidate 0–1 against this RewardSpec" | Zero training, noisy |
| Hand-crafted weighted features | Fixed weights on §9.2 features | Interpretable, brittle |
| Learned regression | Train on historical `(features, observed_reward)` pairs | Sample-efficient when history exists |
| Surrogate model (GP, NN) | Fit per-objective; aggregate per RewardSpec | Strong when objectives are smooth |

Start with LLM-as-evaluator; switch to learned regression once enough history accumulates.

---

## §10. Plan ⟷ Policy Hybrid Architecture

### 10.1 Reconciling §5 (Plan) and §8 (MCTS)

These are **two granularities of the same loop**, not competing approaches:

| Layer | Role | Time scale |
|---|---|---|
| **Plan** (§5) | Coarse-grained directional commitment | Multiple rounds |
| **MCTS** (§8) | Fine-grained action selection within a plan step | Single round |
| **Replan** (§5.2) | Subtree invalidation when MCTS or observation contradicts plan | Triggered |

The plan defines *which region of the search space to expand*; MCTS decides *which action within that region to take next*.

### 10.2 Concrete Coupling

```python
def optimize(state: State, reward_spec: RewardSpec, budget: Budget):
    plan = planner.create_plan(state, reward_spec, horizon=H)
    
    while not terminate(state, budget):
        plan_step = plan.next_step()
        
        # MCTS searches within the action subspace defined by plan_step
        action = mcts_search(
            root=state,
            budget=budget.per_step(),
            action_filter=plan_step.action_subspace,
        )
        
        observation = execute(action, state)
        state = state.advance(action, observation)
        
        plan = planner.update(state, plan, observation)  # §5.2 triggers
        budget.consume(observation.cost)
    
    return state.artifact.incumbent
```

`plan_step.action_subspace` is the bridge: it constrains MCTS expansion to actions consistent with the plan, falling back to the full space when the plan is in "exploratory" mode.

### 10.3 When the Plan Defers

| Plan posture | MCTS scope | When |
|---|---|---|
| Strict | Only actions matching plan_step | High plan confidence, narrow horizon |
| Guided | Plan actions get prior boost; others allowed | Default |
| Open | Plan only sets aggregator/budget; no action filter | Low confidence, exploratory |

The planner picks the posture; this is itself a design decision exposed to the user, not a hardcoded policy.

---

# Part III — Practice

## §11. Domain Instantiations

This section validates that the framework holds across four distinct domains by instantiating §2/§3/§4 for each.

### 11.1 Hypothesis-Test (current optagent)

| Dimension | Instantiation |
|---|---|
| `artifact` | Implemented variant with measured metrics |
| Action kinds | `ProposeHypothesis`, `ImplementHypothesis(h)`, `EvaluateArtifact(a)` |
| Objectives | Domain-specific metric (latency / accuracy / throughput) |
| Constraints | Validity (hard), applicability (hard) |
| Aggregator | WeightedSum or ConstrainedScalar |
| Knowledge | Failed hypothesis patterns, evaluation noise calibration |

This is the v1 case, recovered as a specific instance.

### 11.2 Hyperparameter Optimization (HPO)

| Dimension | Instantiation |
|---|---|
| `artifact` | Config + Pareto front of (config, metric) pairs |
| Action kinds | `SampleConfig(distribution)`, `EvaluateConfig(c)` |
| Objectives | Validation metric (k = 1 typical, k > 1 possible) |
| Constraints | Resource limits (memory, runtime) |
| Aggregator | EHVI for multi-obj; ExpectedImprovement for single |
| Knowledge | GP surrogate over hyperparameter space |

The framework recovers Bayesian optimization when policy = GP-based acquisition function.

### 11.3 Iterative Refinement (e.g., code generation)

| Dimension | Instantiation |
|---|---|
| `artifact` | Current code state + test outcomes |
| Action kinds | `EditArtifact(diff)`, `RunTests(a)`, `RequestExplanation(a)` |
| Objectives | Tests passing, no regressions |
| Constraints | Compilable (hard), no banned patterns (hard) |
| Aggregator | Lexicographic: correctness ≫ test count ≫ style |
| Knowledge | Failing test patterns, regression suite |

Plan posture is typically "Guided" — the plan suggests editing direction, MCTS picks the specific edit.

### 11.4 Compositional Optimization (module assembly)

| Dimension | Instantiation |
|---|---|
| `artifact` | Module DAG + per-slot variant choices |
| Action kinds | `SwapModule(slot, candidate)`, `BenchmarkComposition(graph)` |
| Objectives | End-to-end performance, per-module cost |
| Constraints | Interface compatibility (hard), licensing (hard) |
| Aggregator | Tchebycheff over (latency, cost) |
| Knowledge | Incompatible module pairs, per-slot performance priors |

Pareto-MCTS shines here because slot-level choices are genuinely multi-objective.

---

## §12. Implementation Phases

### Phase 1 — Formalism Layer (Immediate)

1. Implement `State`, `ArtifactSet`, `Transition`, `Knowledge` (§2).
2. Implement `Action` protocol and a hypothesis-test concrete action set (§3, §11.1).
3. Implement `RewardSpec` with WeightedSum and Lexicographic aggregators (§4.4).
4. Refactor `OptimizationState` in current code to wrap §2 schema; preserve back-compat.

### Phase 2 — Planner & Rollout

1. Implement `Planner` interface and `DefaultPlanner` (§5.3).
2. Implement explicit replan triggers (§5.2).
3. Implement budget-bounded rollout (§6).
4. Wire planner into existing `ManagerAgent` workflow.

### Phase 3 — Policy & Value

1. Implement N-sample empirical LLM policy (§7.2).
2. Separate proposer / policy / evaluator prompts (§7.3).
3. Implement LLM-as-evaluator value predictor (§9.3).
4. Begin collecting `(features, reward)` pairs for future learned predictor.

### Phase 4 — MCTS

1. Implement cost-aware UCB1 (§8.3).
2. Implement Pareto-MCTS node structure (§8.2).
3. Implement cost-weighted backprop (§8.5).
4. Wire plan ⟷ MCTS via `action_subspace` (§10.2).

### Phase 5 — Domain Expansion

Instantiate §11.2 / §11.3 / §11.4 to validate framework generality on real workloads.

---

## §13. Open Questions

The following questions remain after v2 (resolved questions from v1 are removed):

1. **Cost estimation accuracy.** `Action.cost()` is itself a prediction. How to calibrate it from observed costs without inflating wall-clock time?

2. **Termination criteria.** When should the search stop? Options: budget exhausted (clear); incumbent stable for K rounds (heuristic); EHVI below ε (principled but ε-dependent). No clear winner.

3. **Multi-agent coordination.** When multiple agents share a knowledge base (§2.4), how to merge `ruled_out_regions` and `surrogate_models` without race conditions or stale data?

4. **Aggregator switching mid-search.** §4.4 / §8.4 allow per-use aggregator choice, but this can produce non-monotonic value estimates across siblings. Is the gain in expressiveness worth the noise?

5. **Plan posture transitions.** §10.3 lists strict / guided / open postures. What signal triggers transitions between them — confidence delta, observation surprise, or user policy?

6. **LLM evaluator self-bias.** When the same LLM proposes and evaluates, does it systematically favor its own proposals? Self-consistency (§7.2) helps but doesn't fully solve.

---

## §14. Related Work

- **AlphaZero** — MCTS + neural network policy (Silver et al., 2017). Structural template for §8.
- **Dreamer** — World models for RL in latent space (Hafner et al., 2019). Inspires the value-predictor framing in §9.
- **Toolformer** — LLMs that learn to use tools (Schick et al., 2023). Relevant for §3 action proposers.
- **LLM+P** — LLM + classical planning (Liu et al., 2023). Comparable to §5 planner design.
- **Pareto-MCTS** — Multi-objective MCTS (Wang & Sebag, 2012). Direct basis for §8.2 / §8.4.
- **BOHB / SMAC** — Bayesian HPO with bandits (Falkner et al., 2018; Hutter et al., 2011). §11.2 reference points.
- **MOEA/D** — Decomposition-based multi-objective evolution (Zhang & Li, 2007). Reference for Tchebycheff aggregator (§4.4).
- **AlphaTensor / FunSearch** — LLM + search for program synthesis (DeepMind, 2022/2024). Comparable framing for §11.3 / §11.4.

---

## §15. Next Steps

1. ✅ **Refactor `OptimizationState`** — Done. v1 code moved to `src/optagent/v1/`, v2 framework in `src/optagent/v2/`.
2. ✅ **Define `RewardSpec`** — Done. User-facing `RewardSpec` with configurable aggregators.
3. ✅ **Implement `Planner` + `DefaultPlanner`** — Done. With explicit replan triggers.
4. ✅ **Prototype LLM-as-evaluator** — Done. `CodeProposer` integrates with OpenCode/Claude backends.
5. ✅ **Implement cost-aware UCB1 MCTS** — Done. With Pareto tracking and incumbent updates.
6. ✅ **Pick one domain from §11.2–§11.4** — Done. §11.3 Code Optimization shipped.
7. **Remaining**: §11.2 HPO, §11.4 Compositional Optimization.

---

# Appendix A — Code Optimization Domain (§11.3) API

## Quick Start

```python
from pathlib import Path
from optagent.v2.domains.code import CodeOptimizer
from optagent.v2.domains.code.backends import OpenCodeBackendAdapter

# Configure backend (OpenCode CLI)
backend = OpenCodeBackendAdapter(
    command="/home/ware10sai/.opencode/bin/opencode",
    timeout=300.0,
)

# Create optimizer
opt = CodeOptimizer(
    source_path=Path("./my_module.py"),
    backend=backend,
)

# Run optimization
result = opt.optimize(
    objective="minimize latency",
    max_rounds=3,
)

# Result: optimized code written back to source_path
print(result.code.content)
```

## How It Works

### Pipeline

```
1. Read source file
2. Baseline benchmark (original code)
3. For each round:
   a. LLM generates optimized code
   b. Apply diff / replace file content
   c. Run pytest (extract test functions from original)
   d. Run timeit benchmark
   e. Keep best if tests pass and latency improves
4. Write best code back to source file
```

### Architecture

```
optagent.v2.domains.code/
  state.py      — CodeState, CodeArtifact (v2.State wrapper)
  action.py     — EditCode, RunTests, RunBenchmark
  reward.py     — Lexicographic: correctness ≫ test_count ≫ style
  proposer.py   — CodeProposer (LLM prompt + response parsing)
  executor.py   — CodeExecutor (patch, pytest, timeit)
  optimizer.py  — CodeOptimizer (main loop)
  backends.py   — OpenCodeBackendAdapter (v1 backend wrapper)
```

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `source_path` | required | Path to Python file to optimize |
| `backend` | `None` | LLM backend (OpenCodeBackendAdapter, ClaudeBackend, or None for mock) |
| `work_dir` | temp dir | Working directory for temp files |
| `objective` | required | Natural language objective (e.g., "minimize latency") |
| `max_rounds` | 5 | Number of optimization rounds |

### Return Value

`CodeState` with fields:
- `code.content` — optimized source code
- `code.test_results` — pytest results (passed, test_count, output)
- `code.benchmark_results` — timeit results (latency_ms, raw_output)
- `code.source_path` — path to optimized file

## Backend Configuration

### OpenCode

```python
from optagent.v2.domains.code.backends import OpenCodeBackendAdapter

backend = OpenCodeBackendAdapter(
    command="/path/to/opencode",
    model="opencode-go/kimi-k2.6",
    timeout=300.0,  # idle timeout (not wall-clock)
)
```

Uses streaming JSONL parsing with idle detection. The timeout resets on each token, so long reasoning/thinking periods do not abort the process.

### Claude

```python
from optagent.v1.backends.claude import ClaudeBackend
from optagent.v2.domains.code.backends import OpenCodeBackendAdapter

v1_backend = ClaudeBackend(model="claude-sonnet")
backend = OpenCodeBackendAdapter(command="claude")  # or wrap similarly
```

### Mock (testing)

```python
opt = CodeOptimizer(source_path=Path("./test.py"), backend=None)
```

Returns mock actions. Useful for testing the pipeline without LLM costs.

## Testing

```bash
# All tests
python3 -m pytest tests/v1/ tests/v2/ -v

# Code domain only
python3 -m pytest tests/v2/test_code_domain.py tests/v2/test_code_proposer.py tests/v2/test_code_optimizer.py -v

# Smoke test with real backend
python3 -m pytest tests/v2/test_code_smoke.py -v -s
```

## Implementation Notes

### Diff vs Complete Replacement

The proposer requests complete optimized code (not unified diffs) from the LLM. The executor detects whether the response is:
- **Complete code** (no `---` header) → direct file replacement
- **Unified diff** → `patch` command application

This avoids `patch` command failures with malformed diffs.

### Test Extraction

Test functions (`def test_*`) are extracted from the original file and appended to the candidate code. This ensures pytest discovers tests even when the optimized code changes function names or signatures.

### Benchmark Isolation

Each candidate is written to a temporary file and benchmarked in isolation. The original file is only overwritten after all rounds complete and the best candidate is selected.

---

*This is a living document. v2 establishes the framework; subsequent revisions should fill in §13 open questions and expand §11 instantiations as they ship.*
