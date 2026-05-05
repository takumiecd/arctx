# Optimization Agent (optagent)

`optagent` is an experimental framework for **auditable optimization loops**.

It is built for code and kernel optimization work where an agent should not only
produce a candidate, but also preserve why it tried the candidate, what happened,
whether the evidence is good enough, and what should be learned for the next
attempt.

```text
Requirement
  -> Hypothesis
  -> Action
  -> Artifact
  -> Observation
  -> Evidence
  -> Decision
  -> Finding
```

The center of the project is the **Evidence Graph**, not a chatbot loop, not a
generic agent framework, and not a search algorithm demo.

## Direction

The project is intentionally narrowing around one strong use case:

> Manage optimization experiments as reproducible evidence graphs, so kernel and
> code optimization attempts can be compared, promoted, rejected, scoped, and
> reused safely.

That means the core product is:

- a canonical schema for attempts, evidence, decisions, and findings
- a JSON/JSONL run store that humans and agents can inspect
- a default hypothesis-test workflow
- promotion gates based on correctness, eligibility, regressions, speedup, and safety
- domain plugins, starting with kernel optimization

Experimental planning/search modules may exist in the repository, but they are not
the architectural center. Search policy is replaceable; evidence and promotion
are not.

## Current Status

| Area | Status | Notes |
| --- | --- | --- |
| `optagent.core` | Active foundation | Canonical Evidence Graph records and `StateStore` |
| Default workflow | Prototype | `ManagerAgent` runs hypothesis -> artifact -> evidence -> decision |
| Storage | Prototype | `run.json`, `requirements.json`, `attempts.jsonl`, `decisions.jsonl`, `findings.jsonl` |
| Kernel domain | Next priority | This is the domain where the architecture should become useful first |
| Code optimizer demos | Experimental | Useful as demos, not the product direction |

## Quick Start

```python
from optagent import ManagerAgent, Requirement

agent = ManagerAgent(work_dir="./runs/demo")

state = agent.optimize(
    Requirement(
        target_type="kernel",
        target_id="csc_linear_forward",
        objective={
            "metric": "latency_ms",
            "direction": "minimize",
            "min_speedup": 1.05,
        },
    )
)

print(state.algorithm.evidence[-1].decision_recommendation)
```

The run directory records both the legacy state file and the Evidence Graph:

```text
runs/demo/
├── run.json
├── requirements.json
├── attempts.jsonl
├── decisions.jsonl
├── findings.jsonl
├── artifacts/
├── raw/
├── reports/
└── state_round_0.json
```

## Repository Map

```text
src/optagent/
├── core/                  # Canonical schema, IDs, JSONL StateStore
├── v1/                    # Current default workflow implementation
│   ├── core/              # ManagerAgent and promotion gate
│   ├── backends/          # Backend adapters
│   ├── evaluation/        # Evaluator interfaces and multi-size aggregation
│   ├── strategies/        # Domain strategy prototypes
│   └── reporting/         # Batch reporting
└── v2/                    # Archived/experimental planning and search code
```

The public direction is `core + workflow + domain plugins`. The `v1` name is
historical; it currently contains the default workflow. The `v2` tree is not the
direction-setting layer.

## Documentation

- [Direction](docs/DIRECTION.md)
- [Agent Model](docs/AGENT_MODEL.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Purpose and Design](docs/PURPOSE_AND_DESIGN.md)
- [Workflow](docs/WORKFLOW.md)
- [State Model](docs/STATE_MODEL.md)

Archived research notes live under `docs/archive/`.

## Development

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q
```

## License

MIT
