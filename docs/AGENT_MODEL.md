# Agent Model

## Core Claim

An optimization agent should behave like an engineer doing controlled
investigation.

The basic loop is not just:

```text
implement -> benchmark -> repeat
```

It is:

```text
investigate -> explain -> hypothesize -> act -> observe -> decide -> learn
```

The important part is that every step changes the agent's state. Even
investigation is an action: it is chosen because the agent believes a particular
measurement, code read, trace, profile, or benchmark slice will reduce
uncertainty.

## State Transition View

The agent always has a current state:

```text
State_t
  = requirement
  + current artifacts
  + observations
  + evidence
  + findings
  + open questions
  + predicted futures
```

Each action is selected because the agent expects it to produce a better next
state:

```text
State_t -- Action_t --> Observation_t --> State_t+1
```

The next state is better if it does at least one of these:

- produces a candidate that can be promoted
- rules out a bad branch
- narrows the applicable scope
- explains a failure
- reduces uncertainty enough to choose the next action
- creates a reusable finding

This means "failed" experiments can still be successful state transitions.

## Investigation Is Also Hypothesis-Driven

Investigation is not passive.

When a human engineer investigates, they are usually testing a question like:

- Is the bottleneck memory access, launch overhead, Python overhead, or dispatch?
- Is the regression shape-specific?
- Is correctness failing because of numerical error or wrong indexing?
- Is the baseline itself unstable?
- Is the apparent win only a benchmark artifact?

So investigation should be represented as actions too:

```text
ProfileWorkload
ReadRelevantCode
RunBaselineMatrix
TraceDispatch
InspectFailureLog
CompareShapeFamilies
CheckNumericalError
```

These actions produce observations. Observations become evidence. Evidence
updates the state.

## Phase Changes

The optimization process changes shape as uncertainty decreases.

### 1. High Uncertainty

At the beginning, the agent does not know the cause.

The loop is investigation-heavy:

```text
investigate -> explain -> hypothesize -> investigate more -> choose direction
```

Useful actions are broad and diagnostic.

### 2. Direction Found

Once the agent has a plausible explanation, it starts trying candidate changes:

```text
hypothesize -> implement -> test -> benchmark -> decide -> learn
```

Here the goal is not only speed. The agent must discover scope:

- where the candidate works
- where it regresses
- what constraints must be attached
- whether it is safe to promote

### 3. Local Refinement

Near the end, the shape of the solution is mostly known.

The loop becomes smaller:

```text
hypothesize -> implement -> verify
```

Investigation does not disappear entirely, but it becomes targeted and cheap.

## Prediction

The agent should not only react to the latest observation. It should maintain
predicted futures.

Example:

```text
If launch overhead is dominant:
  - batching or fused dispatch should help small shapes
  - large shapes may not improve
  - narrower dispatch scope is likely needed

If memory access is dominant:
  - layout changes may help large shapes
  - small shapes may be noise-dominated
  - correctness risk may come from indexing
```

A prediction is useful only if the agent later compares it to reality.

When reality differs from prediction, that is not just failure. It is a signal:

```text
expected: small shapes improve, large shapes neutral
observed: small shapes improve, large shapes regress
update: candidate may need narrower dispatch scope
```

This is why the Evidence Graph needs `Finding`, not just `Decision`.

## Branching, Merging, and Pruning

Optimization is not a single line. It is closer to a branching graph.

```text
baseline
├── branch A: launch overhead hypothesis
│   ├── candidate A1
│   └── candidate A2
├── branch B: memory layout hypothesis
│   └── candidate B1
└── branch C: dispatch bug hypothesis
    └── investigation C1
```

Branches should be pruned when evidence shows they are unpromising or unsafe.
Branches should be merged when two findings explain the same behavior or when two
candidate ideas compose safely.

The agent therefore needs:

- parent attempt ids
- findings attached to attempts
- scope constraints
- decision reasons
- a way to query prior findings before choosing the next action

## Practical Architecture

This leads to a simple architecture:

```text
StateStore
  -> gives history, evidence, findings

KnowledgeStore
  -> retrieves relevant findings and ruled-out regions

Policy
  -> proposes investigation or implementation actions

Executor
  -> runs the action and captures raw output

Evaluator
  -> turns raw output into evidence

PromotionGate
  -> decides accepted/rejected/narrower/more-evidence/unsafe

StateUpdate
  -> writes attempt, decision, and finding
```

Search can be greedy, planner-guided, beam-like, tree-like, or human-guided.
That is secondary. The stable idea is state transition prediction plus evidence
preservation.

## Design Implications

1. Investigation actions are first-class.
2. Implementation actions are first-class.
3. Failed attempts must create findings when they teach something.
4. The agent should record expected outcomes before executing actions.
5. The agent should compare expected and observed outcomes after execution.
6. The state should support branches, merges, and pruning.
7. Promotion is not the same as learning.
8. The mature loop can shrink to hypothesis -> implementation -> verification,
   but the architecture must support returning to investigation when prediction
   fails.

## Why This Model Fits optagent

The current Evidence Graph already has most of the required shape:

```text
Requirement
  -> Attempt
      -> Hypothesis
      -> Action
      -> Artifact
      -> Observation
      -> Evidence
      -> Decision
      -> Finding
```

The next important additions are:

- `expected_observation` on actions or attempts
- `open_questions` in state or knowledge
- `KnowledgeStore` over findings
- investigation action types
- explicit parent/branch relationships
- decision status `unsafe`

This preserves the state-prediction idea while keeping the project grounded in
auditable optimization work.
