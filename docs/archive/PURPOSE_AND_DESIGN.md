# Purpose and Design

## Purpose

optagent exists to make optimization work auditable.

The important output of an optimization agent is not only a faster artifact. It
is the complete record:

- why the agent tried a change
- what action it executed
- what artifact it produced
- what tests and benchmarks observed
- what evidence was normalized from raw output
- why the candidate was accepted, rejected, narrowed, or marked unsafe
- what finding should influence the next attempt

This is the difference between a code-generating agent and an optimization
system.

## Design Position

optagent should be a narrow, strong tool:

> an experiment and evidence layer for code and kernel optimization agents.

It should not become a general agent framework. Generality is useful only when it
preserves the optimization loop:

```text
hypothesis -> artifact -> evidence -> decision -> finding
```

## Why Evidence Comes First

Optimization is full of misleading wins:

- a candidate is faster on one shape but regresses another
- correctness passes on a toy case but fails under real workloads
- a benchmark improves because it skipped work
- an implementation works only for a narrower dispatch scope
- a generated patch touches files outside the intended boundary

The architecture therefore treats evidence and promotion as first-class concepts.

## What The System Should Learn

Failures should not disappear. A rejected attempt can still produce useful
knowledge:

- this hypothesis does not work for the target workload
- this candidate only works for small batch inference
- this file path should not be touched by generated code
- this benchmark is insufficient for promotion
- this dispatch scope needs to be narrowed

Those findings are stored in `findings.jsonl` and should later become a small
`KnowledgeStore`.

## Current Implementation

Today the implementation has:

- `optagent.core`: canonical Evidence Graph schema and JSONL store
- `ManagerAgent`: default hypothesis-test workflow
- `PromotionGate`: correctness, eligibility, regression, and speedup decision logic
- v1 backend/evaluator/strategy interfaces
- experimental planning/search code kept outside the main direction

The current naming still reflects repo history. The intended architecture is
`core + workflows + domains + execution + storage`.

## Kernel Optimization Focus

Kernel optimization should drive the next phase.

It forces optagent to solve real problems:

- baseline selection
- correctness by workload
- latency by shape family
- regression detection
- dispatch eligibility
- narrowed promotion scope
- raw benchmark preservation

That is where optagent can become meaningfully different from a generic coding
agent.
