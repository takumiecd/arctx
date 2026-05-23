# STAG

STAG is a Python library for recording the process of problem-solving and optimization as DAGs and JSONL.

It aims to preserve not just final results, but also the plans made along the way, predictions before execution, and what actually happened. Currently at 0.1 alpha — model refinement is prioritized over backward compatibility. No guarantees for old run storage formats or legacy APIs.

*日本語版は [README.ja.md](README.ja.md) を参照してください。*

## What It Builds

What STAG builds is an append-only history graph for the optimization process.

In code optimization, kernel optimization, experiments, and investigation, the final artifact alone is not enough — what you tried, what you predicted, and what actually happened are essential. STAG preserves that trial-and-error process as `RunGraph` and payloads.

The CLI and Python API are entry points for manipulating this history graph. `init` creates a run, `plan` records the next attempt, `predict` leaves pre-execution expectations, and `observe` saves measured results. `trace` and `show` are used to read back the preserved decision-making process.

STAG itself is not an executor or code generator. It is a foundation for structurally preserving the decisions and results made by humans, LLMs, scripts, benchmark runners, and executors — so they can be shared and reviewed later.

## Model

The center of 0.1 is `RunGraph`. `RunGraph` holds the DAG for the entire run, and `GraphView` represents a subset of it.

```text
RunHandle
  └── run_graph: RunGraph

RunGraph
  ├── nodes
  ├── input_transitions
  ├── output_transitions
  ├── payloads
  └── views

GraphView
  ├── view_id
  └── root_node_id
```

`InputTransition` is the input-side transition that accepts multiple input nodes. `PlanPayload` is attached here. `OutputTransition` is the output-side transition that reaches a single output node. `PredictionPayload` / `ResultPayload` are attached here.

Lightweight memos can be attached to nodes as `NotePayload`.

`RunGraph` is append-only. Once added, nodes / input transitions / output transitions / payloads are never deleted. Cancellation and invalidation are expressed through `CutPayload` and read-time computation.

## Quick Start

```python
import stag
from stag import PlanPayload, Requirement, ResultPayload
from stag.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_kernel",
    target_type="kernel",
    target_id="csc_linear",
)

run = stag.init(requirement, run_id="demo")

input_transition = run.plan(
    [run.root_node_id],
    PlanPayload(
        payload_id="pending",
        target_id="pending",
        intent="run baseline benchmark",
    ),
)

prediction = run.predict(input_transition.input_transition_id, max_outcomes=1)[0]

observed = run.observe(
    input_transition.input_transition_id,
    ResultPayload(
        payload_id="pending",
        target_id="pending",
        status="completed",
        raw_outputs=("raw/profile.txt",),
        metrics={"latency_ms": 1.5},
        matched_prediction_output_id=prediction.output_transition_id,
    ),
)

history = run.trace(observed.to_node_id)

store = JsonlRunStore("runs")
run.save(store)
loaded = store.load_run("demo")
```

For isolated exploration, create a `GraphView`. `GraphView` holds only a `root_node_id` — its contents are computed at read-time via `RunGraph.reachable_from(root_node_id)`.

## Install

Python 3.10 or later is required.

When working from a development checkout, do an editable install from the repo root:

```bash
python3 -m pip install -e .
```

To also install dev dependencies:

```bash
python3 -m pip install -e ".[dev]"
```

Without installing, you can run as a module from the repo root:

```bash
PYTHONPATH=src python3 -m stag.cli.main ...
```

## CLI Quick Start

To explore concepts and the basic loop from the CLI:

```bash
stag guide
```

For Japanese output, use `stag guide --lang ja`.

```bash
stag init req_kernel \
  --target-type kernel \
  --target-id csc_linear \
  --run-id demo

stag plan \
  --run demo \
  --input-node <root_node_id> \
  --intent "run baseline benchmark"

stag predict \
  --run demo \
  <input_transition_id> \
  --max-outcomes 1

stag observe \
  --run demo \
  <input_transition_id> \
  --matched-prediction <prediction_output_transition_id> \
  --status completed \
  --raw-output raw/profile.txt \
  --metric latency_ms=1.5

stag trace --run demo --from-node <observed_node_id>
stag show --run demo
```

If not installed, replace each command with `PYTHONPATH=src python3 -m stag.cli.main ...`.

## Key Terms

- `Requirement`: the goal of a run.
- `RunGraph`: the overall DAG and global records for a run.
- `GraphView`: a subset of `RunGraph`.
- `Node`: a pure graph node.
- `InputTransition`: an input-side transition accepting multiple input nodes.
- `OutputTransition`: an output-side transition that reaches a single output node.
- `NotePayload`: a lightweight memo attached to a node.
- `PlanPayload`: plan information attached to an `InputTransition`.
- `PredictionPayload`: prediction information attached to a prediction output.
- `ResultPayload`: execution result attached to an observed output.
- `CutPayload`: an append-only payload that marks an input/output transition as inactive.

## Storage Format

`JsonlRunStore` persists a run as a directory:

```text
<store-dir>/<run-id>/
  run.json
  graph.json
  views.jsonl
  nodes.jsonl
  input_transitions.jsonl
  output_transitions.jsonl
  payloads.jsonl
```

In 0.1 alpha, the storage format may change in breaking ways. Read compatibility with old `states.jsonl` / `execution_plans.jsonl` formats is not provided.

## Documentation

- [Concept](docs/en/CONCEPT.md)
- [Project Direction](docs/en/DIRECTION.md)
- [State Model](docs/en/STATE_MODEL.md)
- [API](docs/en/API.md)
- [CLI](docs/en/CLI.md)
- [Problem-Solving Loop](docs/en/AGENT_LOOP.md)

日本語ドキュメントは [docs/ja/](docs/ja/) にあります。

## Development

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q
```

## License

MIT
