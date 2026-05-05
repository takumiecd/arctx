# Project Direction

## North Star

optagent is an evidence system for optimization agents.

The goal is not to build a general agent framework. The goal is to make
optimization attempts reproducible, comparable, and reusable:

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

If an optimization attempt cannot explain why it was tried, what evidence it
produced, why it was accepted or rejected, and what should be learned from it,
then optagent has not done its job.

The agent model is described in [Agent Model](AGENT_MODEL.md). The short version:
optimization is a state-transition process where investigation, implementation,
verification, and failure analysis are all actions that update what the agent
knows.

## Product Shape

The stable architecture should be:

```text
optagent
├── core
│   ├── canonical schema
│   ├── Evidence Graph
│   ├── PromotionGate inputs/outputs
│   └── StateStore
├── workflows
│   └── hypothesis-test workflow
├── domains
│   ├── kernel
│   └── code
├── execution
│   ├── backend adapters
│   ├── executors
│   ├── evaluators
│   └── sandbox/worktree policy
└── storage
    ├── run directories
    ├── artifacts
    ├── raw outputs
    ├── evidence
    └── findings
```

The current code still contains historical `v1` and experimental `v2` packages.
Treat those names as implementation history, not product architecture.

## What Is Core

These concepts are non-negotiable:

- `Requirement`: fixed target, objective, constraints, and promotion policy
- `Attempt`: one node in the Evidence Graph
- `Action`: the replayable unit of work, cost, and observation
- `Artifact`: candidate output produced by an action
- `Observation`: raw measured result
- `Evidence`: normalized facts used for decisions
- `Decision`: promotion outcome with reason and policy
- `Finding`: reusable knowledge for future attempts
- `StateStore`: human-readable persistence for all of the above

Search algorithms, planners, LLM backends, and domain-specific heuristics are
replaceable.

## First-Class Workflow

The default workflow is hypothesis testing:

```text
resolve target and baseline
  -> propose hypotheses
  -> review hypotheses
  -> build isolated artifacts
  -> execute tests and benchmarks
  -> normalize evidence
  -> apply PromotionGate
  -> write findings
```

This workflow should stay boring, inspectable, and deterministic around the
edges. LLMs can propose and generate, but the workflow owns evidence and
promotion.

## Storage Contract

Start with JSON and JSONL. Do not introduce a database until the file contract is
boring and stable.

```text
runs/<run_id>/
├── run.json
├── requirements.json
├── attempts.jsonl
├── decisions.jsonl
├── findings.jsonl
├── artifacts/
├── raw/
└── reports/
```

This format is intentionally simple:

- human-readable
- git-friendly
- easy for agents to inspect
- easy to migrate later to SQLite or DuckDB

## Domain Priority

Kernel optimization should be the first serious domain.

It fits optagent better than a generic code optimizer because kernel promotion
depends on evidence by dispatch key, shape family, dtype, device, correctness,
latency, regressions, and eligibility scope.

The first kernel-domain target should support:

- benchmark command execution
- correctness command execution
- latency parsed by shape or workload
- geometric mean speedup
- regression detection
- `accepted`, `rejected`, `needs_narrower_scope`, `needs_more_evidence`, `unsafe`

## Non-Goals

optagent is not:

- a general chatbot framework
- a LangChain-style agent framework
- a code generator with benchmarks bolted on
- an MCTS-first research demo
- a tool that writes optimized code back into source by default

Automatic write-back should remain off by default. Candidate changes should be
stored as patches, artifacts, or isolated worktrees until explicitly promoted.

## Near-Term Plan

1. Keep `core` as the canonical schema and storage layer.
2. Make `PromotionGate` return canonical `DecisionRecord` objects.
3. Add a small `KnowledgeStore` over `findings.jsonl`.
4. Split executor and evaluator responsibilities clearly.
5. Build a minimal kernel domain around external correctness and benchmark commands.
6. Treat older planning/search material as archived research until it directly serves the workflow.
