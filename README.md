# STAG

STAG is a Python library for recording the process of problem-solving and optimization as DAGs and JSONL.

It aims to preserve not just final results, but also the plans made along the way, predictions before execution, and what actually happened. Currently at 0.1 alpha — model refinement is prioritized over backward compatibility. No guarantees for old run storage formats or legacy APIs.

*日本語版は [README.ja.md](README.ja.md) を参照してください。*

## What It Builds

What STAG builds is an append-only history graph for the optimization process.

In code optimization, kernel optimization, experiments, and investigation, the final artifact alone is not enough — what you tried, what you predicted, and what actually happened are essential. STAG preserves that trial-and-error process as `RunGraph` and payloads.

The CLI and Python API are entry points for manipulating this history graph. `init` creates a run, `transition create` records the next graph transition and creates its output node, `payload add` attaches domain data, and `graph trace` / `show` read back the preserved decision-making process.

STAG itself is not an executor or code generator. It is a foundation for structurally preserving the decisions and results made by humans, LLMs, scripts, benchmark runners, and executors — so they can be shared and reviewed later.

## Model

The center of 0.1 is `RunGraph`. `RunGraph` holds the DAG for the entire run, and `GraphView` represents a subset of it.

```text
RunHandle
  └── run_graph: RunGraph

RunGraph
  ├── nodes
  ├── transitions
  ├── payloads
  └── views

GraphView
  ├── view_id
  └── root_node_id
```

`Transition` connects many input nodes to exactly one output node. Domain meaning is attached separately through payloads. Generic `NodePayload` and `TransitionPayload` are flexible; special payloads such as `CutPayload` and `GitChangePayload` carry built-in semantics.

`RunGraph` is append-only. Once added, nodes / input transitions / output transitions / payloads are never deleted. Cancellation and invalidation are expressed through `CutPayload` and read-time computation.

## Quick Start

```python
import stag
from stag import NodePayload, Requirement, TransitionPayload
from stag.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_kernel",
    target_type="kernel",
    target_id="csc_linear",
)

run = stag.init(requirement, run_id="demo")

transition = run.transition(
    [run.root_node_id],
    TransitionPayload(
        payload_id="pending",
        target_id="pending",
        type="experiment",
        content={"intent": "run baseline benchmark"},
    ),
)

run.attach(
    transition.output_node_id,
    NodePayload(
        payload_id="pending",
        target_id="pending",
        type="result",
        content={"latency_ms": 1.5, "status": "completed"},
    ),
)

history = run.trace(transition.output_node_id)

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

stag transition create \
  --run demo \
  --from <root_node_id> \
  --payload-type transition_payload \
  --field type=experiment \
  --field intent="run baseline benchmark"

For parallel terminals or child processes, split history by work session. Use
explicit mode when you want every command to be self-contained:

```bash
stag transition create \
  --run demo \
  --work-session ws_a \
  --from <root_node_id> \
  --payload-type transition_payload \
  --field type=experiment
```

Use fixed mode when a terminal or subprocess should keep using one session.
This pins only shell environment variables and does not update shared
`current.json` state:

```bash
eval "$(stag work-session env --run demo --new)"
stag transition create --from <root_node_id> --payload-type transition_payload
stag work-session spawn --run demo -- codex
```

stag payload add \
  --run demo \
  --node <output_node_id> \
  --payload-type node_payload \
  --field type=result \
  --field latency_ms=1.5

stag graph trace --run demo <output_node_id>
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
