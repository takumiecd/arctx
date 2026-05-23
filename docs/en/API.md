# API

This document describes the Python API targeted in 0.1 alpha. Breaking changes are accepted and compatibility with old APIs is not maintained.

## Minimal Example

```python
import stag
from stag import PlanPayload, Requirement, ResultPayload

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
        intent="run benchmark",
        inputs={"shape": "small"},
    ),
)

prediction = run.predict(input_transition.input_transition_id, max_outcomes=1)[0]

observed = run.observe(
    input_transition.input_transition_id,
    ResultPayload(
        payload_id="pending",
        target_id="pending",
        status="completed",
        raw_outputs=("raw/bench.txt",),
        metrics={"latency_ms": 1.5},
        matched_prediction_output_id=prediction.output_transition_id,
    ),
)

history = run.trace(observed.to_node_id)
```

## Public Dataclasses

Main public models:

- `Requirement`
- `RunGraph`
- `GraphView`
- `Node`
- `InputTransition`
- `OutputTransition`
- `PayloadBase`
- `NotePayload`
- `PlanPayload`
- `PredictionPayload`
- `ResultPayload`
- `CutPayload`
- `TraceContext`

`Dag` is not used as a name for the overall graph — it is replaced by `RunGraph`. Subsets are `GraphView`.

`Plan` is not used as a graph record. Plan information is `PlanPayload` attached to an `InputTransition`.

`SnapshotPayload` / `DerivedPayload` / `MatchPayload` / `PredictionSelection` / `PredictionPath` are excluded from the 0.1 minimal API.

## `stag.init`

```python
stag.init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle
```

Creates a new run.

What is created:

- `run.run_graph`: the overall `RunGraph` for the run
- `run.run_graph.views["main"]`: the default `GraphView` rooted at `run.root_node_id`
- root node: `run.root_node_id`

## `run.plan`

```python
run.plan(
    input_node_ids: list[str] | tuple[str, ...],
    payload: PlanPayload,
    *,
    user_id: str | None = None,
) -> InputTransition
```

Accepts multiple input nodes and creates an `InputTransition`. Plan intent, inputs, constraints, assumptions, etc. are attached to that input transition as `PlanPayload`.

Passing downstream nodes of a cut input transition or inactive nodes raises `ValueError`.

## `run.note`

```python
run.note(
    node_id: str,
    text: str,
    *,
    tags: list[str] | tuple[str, ...] = (),
    user_id: str | None = None,
) -> NotePayload
```

Attaches a lightweight memo as `NotePayload` to a node. Existing nodes and transitions are not modified.

## `run.predict`

```python
run.predict(
    input_transition_id: str,
    *,
    payloads: list[PredictionPayload] | None = None,
    max_outcomes: int | None = None,
    user_id: str | None = None,
) -> list[OutputTransition]
```

Creates prediction output `OutputTransition`s. Each output transition has a `PredictionPayload` attached.

Raises `ValueError` for inactive input transitions (directly cut or whose input node is inactive). If a `ResultPayload` is already attached to the same OT, attaching a `PredictionPayload` raises `ValueError`.

## `run.observe`

```python
run.observe(
    input_transition_id: str,
    result: ResultPayload,
    *,
    user_id: str | None = None,
) -> OutputTransition
```

Records an execution result as an observed output `OutputTransition`. Attaches `ResultPayload` to the new output transition. If a `PredictionPayload` is already attached to the same OT, attaching a `ResultPayload` raises `ValueError`.

The correspondence between prediction and observation is expressed via `ResultPayload.matched_prediction_output_id`. When `matched_prediction_output_id` is specified, the OT must be an active prediction from the same input transition. Violations raise `KeyError` or `ValueError`:

- Non-existent OT ID → `KeyError`
- OT without `PredictionPayload` → `ValueError("matched_prediction_output_id does not point to a prediction: ...")`
- OT belonging to a different input transition → `ValueError("matched_prediction_output_id belongs to a different input_transition: ...")`
- Inactive prediction OT → `ValueError("matched_prediction_output_id is inactive: ...")`

Multiple prediction outputs and multiple observed outputs can be created from a single input transition. For operations where results vary stochastically, multiple observed outputs can be recorded side by side under the same input transition.

Raises `ValueError` for inactive input transitions (directly cut or whose input node is inactive).

`run.result(...)` is an alias for `run.observe(...)`.

## `run.outcomes`

```python
run.outcomes(
    input_transition_id: str,
) -> dict
```

Classifies and returns all output transitions associated with a single input transition.

```python
{
    "input_transition_id": "it_xxxx",
    "predictions": [...],          # OTs with PredictionPayload (active or inactive)
    "observations": [...],         # OTs with ResultPayload (active or inactive)
    "active_observations": [...],  # non-inactive ResultPayload OTs
    "inactive_observations": [...] # ResultPayload OTs made inactive by cut
}
```

Raises `KeyError` if the input_transition_id is unknown.

## `run.cut`

```python
run.cut(
    target_id: str,
    *,
    target_kind: Literal["input_transition", "output_transition"],
    reason: str | None = None,
    user_id: str | None = None,
) -> CutPayload
```

Attaches a `CutPayload`. Existing records are not deleted.

`target_kind="input_transition"` makes the entire plan inactive. `target_kind="output_transition"` makes only that prediction/result output inactive.

## `run.trace`

```python
run.trace(
    node_id: str,
    *,
    depth: int | None = None,
    include_predictions: bool = False,
    include_raw_refs: bool = True,
) -> TraceContext
```

Traverses past observed history from the node via backward BFS.

- Enqueues all `input_node_ids` of multi-input ITs, correctly collecting all ancestors even from merge nodes with multiple parents.
- Inactive observed OTs (rewound) are not traversed.
- Collection fields of the returned `TraceContext` (`past_node_ids`, `output_transition_ids`, `input_transition_ids`, `result_payload_ids`, `prediction_output_transition_ids`, `note_payload_ids`) are ascending sorted tuples in deterministic order. `artifact_refs` is a deduplicated tuple preserving appearance order.
- `depth` is the number of backward steps. Step 0 is `node_id` itself, `depth=1` up to direct parents. `None` for all ancestors.
- When `include_predictions=False`, only observed OTs are collected. `run.history(...)` is an alias.

## GraphView API

```python
run.view_create(name: str, *, root_node_id: str) -> GraphView
run.view_list() -> list[GraphView]
run.view_show(name: str) -> GraphView
```

View contents are computed at read-time via `run.run_graph.reachable_from(view.root_node_id)`.

```python
run.run_graph.reachable_from(node_id: str) -> dict
# Returns: {"node_ids": [...], "input_transition_ids": [...],
#           "output_transition_ids": [...], "payload_ids": [...]}
```

To "integrate a view", simply add an `OutputTransition` from a node in the target to the `root_node_id` of the source via normal `plan` / `observe`. `view_merge` has been removed.

## Storage

```python
from stag.storage import JsonlRunStore

store = JsonlRunStore("runs")
run.save(store)
loaded = store.load_run("demo")
```

Files saved:

- `run.json`
- `graph.json`
- `views.jsonl`
- `nodes.jsonl`
- `input_transitions.jsonl`
- `output_transitions.jsonl`
- `payloads.jsonl`

In 0.1 alpha, there is no read compatibility with old storage schemas.
