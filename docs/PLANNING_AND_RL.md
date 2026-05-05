# Planning and Reinforcement Learning Integration

## Overview

This document captures the architectural vision for integrating **planning**, **state prediction**, and **reinforcement learning (RL)** concepts into the optagent framework.

The core insight: instead of treating optimization as a one-shot hypothesis-test-evaluate loop, we frame it as a **state transition prediction problem** — analogous to next-token prediction in LLMs, but at the level of optimization states.

---

## 1. Philosophy: Optimization as State Transition Prediction

### Current Model

```
X_t = (R, H_{<t}, C_{<t})
        ↓ predict
X_{t+1} = (R, H_{≤t}, C_{≤t})
```

Where:
- **R**: Requirement (fixed)
- **H**: Hypotheses generated so far
- **C**: Evidence collected so far

The agent must predict: **"What is the optimal next state/action?"**

### Analogy to LLM Next-Token Prediction

Just as LLMs predict the next token given context, the planner predicts the next optimization action given the current state:

| LLM | Optimization Agent |
|-----|-------------------|
| Token sequence | State trajectory |
| P(next_token \| context) | P(next_action \| state) |
| Autoregressive generation | Sequential hypothesis testing |
| Training on text corpus | Learning from optimization history |

---

## 2. Planner Component

### 2.1 Core Interface

```python
class Planner:
    """Predicts the next optimal state X_{t+1} from current state X_t."""
    
    def predict_next_state(self, X_t: OptimizationState) -> StatePrediction:
        """
        Outputs:
        - Candidate next states
        - Expected value for each (speedup expectation, risk)
        - Recommended action
        """
        pass
    
    def update_plan(self, X_t: OptimizationState, actual_C_t: Evidence) -> Plan:
        """
        Receives actual evidence C_t and updates the plan.
        If prediction diverges from reality, replan.
        """
        pass
```

### 2.2 State Prediction Structure

```python
@dataclass
class StatePrediction:
    candidates: List[PredictedState]
    recommended_action: str
    confidence: float
    
@dataclass
class PredictedState:
    action: str  # "propose", "implement", "evaluate", etc.
    target: str
    expected_result: str
    estimated_speedup: float
    risk_score: float
```

---

## 3. Rollout: Virtual Future Expansion

### Concept

Like game AI "reading ahead", we simulate future trajectories:

```python
def rollout(state: OptimizationState, depth: int = 3) -> List[FuturePath]:
    """
    Virtually expand future from current state.
    
    Each path predicts expected final speedup.
    
    Example:
    Path A: h1 → implement → evaluate → accepted → promote
            Expected speedup: 1.3x, Risk: LOW
            
    Path B: h2 → implement → evaluate → rejected → retry
            Expected speedup: 1.5x, Risk: HIGH (uncertainty)
    """
```

### Why It Helps

Determines **which hypothesis to try first** by reading multiple moves ahead, not just evaluating immediate gains.

---

## 4. Plan Structure

### 4.1 Plan as Trajectory

```python
@dataclass
class Plan:
    steps: List[PlannedStep]
    expected_outcome: Prediction
    fallback_plans: List[Plan]
    confidence: float
    assumptions: List[str]  # Preconditions to verify
    
@dataclass
class PlannedStep:
    action: str
    target: str
    expected_result: str
    checkpoint: str  # Decision point after this step
```

### 4.2 Adaptive Replanning

```python
class AdaptivePlanner:
    def execute_with_plan(self, state: OptimizationState, plan: Plan):
        for step in plan.steps:
            result = self.execute_step(step, state)
            
            deviation = self.check_deviation(step.expected_result, result)
            if deviation > threshold:
                # Prediction diverged → replan
                plan = self.replan(state, result, plan.fallback_plans)
                self.log_replan("Deviation detected", deviation, plan)
```

**Key idea**: Plans are loose and frequently updated. Like human planning — you have a direction but adapt continuously.

---

## 5. LLM-Based State Prediction

### Using LLM for Next-State Prediction

```python
class LLMStatePredictor:
    def predict(self, X_t: OptimizationState) -> StatePrediction:
        prompt = f"""
Current state:
- Round: {X_t.round_index}
- Past hypotheses: {[h.claim for h in X_t.hypotheses]}
- Past evidence: {[e.decision_recommendation for e in X_t.evidence]}

Predict the optimal next action:
1. Next hypothesis direction
2. Expected artifact type
3. Predicted evaluation result
4. Recommended decision
5. Risks and alternatives

Output as JSON.
"""
        prediction = self.llm.generate(prompt)
        return self.parse_prediction(prediction)
```

**Advantage**: Leverages LLM's pre-trained reasoning without fine-tuning.

---

## 6. RL Integration: MCTS + Fixed LLM Policy

### 6.1 Core Concept

> **Use pre-trained LLM as a fixed policy π, and apply RL for exploration/evaluation.**

This is structurally identical to AlphaZero:

| AlphaZero | Kernel Optimization |
|-----------|---------------------|
| Policy network (trained) | LLM (pre-trained, fixed) |
| MCTS (exploration) | Hypothesis tree search |
| Win/loss (reward) | Speedup × correctness (reward) |

### 6.2 Why This Works

1. **Reward is naturally defined**
   ```
   Reward = speedup × correctness × eligibility
          = (baseline_ms / candidate_ms) × 1{correct} × 1{eligible}
   ```
   
2. **Search space is structured**
   ```
   X_t
   / | \
  h1 h2 h3   ← LLM generates (policy π)
  / | \
  X_{t+1} X_{t+1} X_{t+1}   ← Implementation + evaluation (environment)
  | | |
  h1.1 h2.1 h3.1
   ```

3. **LLM stays fixed**
   No fine-tuning needed. Only the exploration strategy changes.

### 6.3 MCTS Optimizer

```python
class MCTSOptimizer:
    def __init__(self, llm_policy, reward_fn):
        self.policy = llm_policy      # Fixed LLM
        self.reward = reward_fn       # Speedup measurement
    
    def search(self, state: OptimizationState, n_simulations: int = 10):
        for _ in range(n_simulations):
            # Selection: UCB1
            node = self.select(state)
            
            # Expansion: LLM generates hypotheses
            children = self.policy.generate_hypotheses(node)
            
            # Simulation: Lightweight prediction
            for child in children:
                predicted_reward = self.predict_reward(child)
            
            # Backpropagation
            self.backpropagate(node, predicted_reward)
        
        return self.best_child(state)
```

### 6.4 Value Predictor (Lightweight)

Evaluating every hypothesis is expensive. Use a lightweight predictor:

```python
class ValuePredictor:
    """Lightweight hypothesis value prediction before full evaluation."""
    
    def predict(self, hypothesis: Hypothesis, state: OptimizationState) -> float:
        features = {
            'similarity_to_past_winners': ...,   # Has this worked before?
            'complexity_estimate': ...,           # How complex is the change?
            'risk_score': ...,                    # Probability of failure
            'expected_compile_success': ...,      # Will it compile?
        }
        return self.model.predict(features)
```

This filters unpromising hypotheses before expensive compilation/benchmarking.

---

## 7. Extended State Model

### Adding Policy and Value to State

```python
@dataclass
class OptimizationState:
    # Existing fields
    round_index: int
    requirement: Requirement
    hypotheses: List[Hypothesis]
    artifacts: List[Artifact]
    evidence: List[Evidence]
    decisions: List[Decision]
    
    # RL extensions
    policy: Policy          # LLM policy (fixed or learned)
    value_estimate: float   # Current value estimate
    visit_count: int        # For MCTS
```

### State Transition

```
X_t = (R, H_{<t}, C_{<t}, π_t, V_t)
        ↓ a_t (action from planner)
X_{t+1} = (R, H_{≤t}, C_{≤t}, π_{t+1}, V_{t+1})
```

---

## 8. Implementation Phases

### Phase 1: Planner Component (Immediate)

Add `Planner` to `ManagerAgent`:

```python
class ManagerAgent:
    def __init__(self, ..., planner: Planner = None):
        self.planner = planner or DefaultPlanner()
    
    def optimize(self, requirement):
        state = self.initialize_state(requirement)
        plan = self.planner.create_plan(state)
        
        while not plan.is_complete():
            step = plan.next_step()
            result = self.execute_step(step, state)
            plan = self.planner.update_plan(state, result, plan)
            state = state.advance(...)
```

### Phase 2: Rollout Simulation (Short-term)

```python
class RolloutSimulator:
    def simulate(self, state, hypothesis, depth=3) -> ExpectedOutcome:
        """Simulate future if this hypothesis is adopted."""
        for d in range(depth):
            predicted_evidence = self.predict_evidence(state, hypothesis)
            if predicted_evidence.decision == "rejected":
                return ExpectedOutcome(success=False)
            state = state.advance(...)
        return ExpectedOutcome(success=True, expected_speedup=...)
```

### Phase 3: MCTS Integration (Long-term)

Full tree search with:
- UCB1 selection
- LLM expansion
- Lightweight simulation
- Backpropagation

---

## 9. Key Design Decisions

### 9.1 Why Post-hoc RL?

> "Apply RL concepts to a pre-trained model after the fact"

- **Flexibility**: Can change exploration strategy without retraining
- **Data efficiency**: No need for massive optimization datasets
- **Safety**: Fixed LLM preserves general capabilities

### 9.2 Why MCTS?

- Handles **sparse rewards** (only get reward after full evaluation)
- Balances **exploration vs exploitation**
- **Theoretically grounded** (UCT convergence guarantees)

### 9.3 Plan Flexibility

> "Plans should be loose and change frequently"

Like human planning:
- Have a direction
- Adapt continuously
- Don't over-commit to early decisions

---

## 10. Open Questions

1. **How to represent state for LLM prediction?**
   - JSON serialization?
   - Structured prompt?
   - Embedding-based?

2. **How to build the value predictor?**
   - Hand-crafted features?
   - Learned from optimization history?
   - LLM-based estimation?

3. **When to trigger replanning?**
   - Fixed deviation threshold?
   - Adaptive based on uncertainty?
   - User-defined?

4. **How to balance exploration depth vs cost?**
   - Full evaluation is expensive
   - Lightweight prediction may be inaccurate
   - Need cost-aware search

---

## 11. Related Work

- **AlphaZero**: MCTS + neural network policy (Silver et al., 2017)
- **Dreamer**: World models for RL in latent space (Hafner et al., 2019)
- **Toolformer**: LLMs that learn to use tools (Schick et al., 2023)
- **LLM+P**: LLM + classical planning (Liu et al., 2023)

---

## 12. Next Steps

1. Implement `Planner` interface and `DefaultPlanner`
2. Add `Plan` and `PlannedStep` data structures
3. Integrate planner into `ManagerAgent` workflow
4. Implement basic rollout simulation
5. Collect optimization history for value predictor training
6. Prototype MCTS with lightweight simulation

---

*This is a living document. As we implement and learn, update with findings and revise design decisions.*
