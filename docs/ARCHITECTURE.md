# optagent Architecture

## Overview

optagent is organized around the Evidence Graph.

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

The architecture is intentionally not centered on a manager class, a planner, an
LLM backend, or a tree-search algorithm. Those are implementation choices. The
Evidence Graph is the durable product.

## Layers

```text
src/optagent/
├── core/
│   ├── ids.py
│   ├── schema.py
│   └── store.py
├── v1/
│   ├── core/
│   ├── backends/
│   ├── evaluation/
│   ├── strategies/
│   └── reporting/
└── v2/
```

The current package names are historical:

- `core/` is the canonical layer.
- `v1/` contains the current default workflow implementation.
- `v2/` contains experimental planning/search code. It is not the architectural center.

Future cleanup should introduce product-oriented package names such as
`workflows/`, `domains/`, and `execution/`, then migrate code into them gradually.

## Core Layer

`optagent.core` defines the records that all workflows should write:

- `RequirementRecord`
- `AttemptRecord`
- `HypothesisRecord`
- `ActionRecord`
- `ArtifactRecord`
- `ObservationRecord`
- `EvidenceRecord`
- `DecisionRecord`
- `FindingRecord`
- `StateStore`

These records are JSON-friendly dataclasses. Domain-specific details should go in
`metadata` until they are stable enough to become typed fields.

## Default Workflow

The current default workflow is implemented by `ManagerAgent`.

```text
resolve target and baseline
  -> generate hypotheses
  -> review hypotheses
  -> build artifacts
  -> evaluate artifacts
  -> apply promotion gate
  -> analyze results
  -> save state and Evidence Graph records
```

`ManagerAgent` should remain an orchestrator. It should not become the place
where domain logic, execution logic, evaluation parsing, and promotion policy all
live.

## Execution vs Evaluation

These responsibilities should stay separate:

```text
Executor
  - runs an action
  - creates artifacts
  - captures raw output
  - enforces timeout/path/worktree policy

Evaluator
  - parses raw output
  - checks correctness facts
  - compares against baseline
  - computes speedup/regressions
  - emits EvidenceRecord
```

This separation matters because kernel benchmarks often run in a different
environment from the code that decides promotion.

## Promotion Gate

Promotion is the decision boundary.

Canonical decision statuses:

- `accepted`
- `rejected`
- `needs_narrower_scope`
- `needs_more_evidence`
- `unsafe`

The gate should consider at least:

- correctness
- eligibility
- regressions
- minimum speedup
- benchmark/raw-output quality
- unsafe file changes or execution behavior

## Storage Layout

Each run should be self-contained:

```text
runs/<run_id>/
├── run.json
├── requirements.json
├── attempts.jsonl
├── decisions.jsonl
├── findings.jsonl
├── artifacts/
├── raw/
├── reports/
└── state_round_*.json
```

`state_round_*.json` exists for current workflow compatibility. The long-term
stable interface is the Evidence Graph JSON/JSONL files.

## Domain Direction

The first serious domain should be kernel optimization.

Minimum useful kernel domain:

- accepts target operation, dtype, device, shape family, dispatch keys
- runs external correctness and benchmark commands
- parses latency by shape/workload
- computes geometric mean speedup
- detects regressions
- recommends narrowed dispatch scope when needed
- writes all evidence and findings into the run store

Generic code optimization remains useful as a demo, but the project should not be
designed around arbitrary source rewrite.

## Safety Policy

Default behavior should never write optimized code back into source.

Allowed output modes should be explicit:

- no write-back
- patch only
- candidate directory
- isolated worktree
- branch
- in-place only after explicit promotion

Unsafe attempts should produce `DecisionRecord(status="unsafe")`, not just a
generic rejection.
