# Problem-Solving Loop

optagent is not an agent itself. It is a foundation that structurally stores plans, predictions, and execution results so that humans, AIs, scripts, and executors can share the same context.

## Basic Cycle

```text
Select input nodes
  -> Leave NotePayload on nodes if needed
  -> Create InputTransition + PlanPayload
  -> Create prediction outputs and PredictionPayload if needed
  -> Execute outside of optagent
  -> Save results as observed outputs and ResultPayload
  -> Read history via trace
  -> Create GraphView for isolated exploration if needed
```

## 1. Select Input Nodes

The core does not maintain a mutable current pointer. The caller explicitly specifies input nodes.

```python
input_node_ids = [run.root_node_id]
```

## 2. Create a Plan

Plan information is `PlanPayload`, not a graph record. `run.plan(...)` creates an `InputTransition` and attaches a `PlanPayload` to it.

```python
input_transition = run.plan(
    input_node_ids,
    PlanPayload(
        payload_id="pending",
        target_id="pending",
        intent="run benchmark",
    ),
)
```

Lightweight memos can be left on nodes as needed.

```python
run.note(run.root_node_id, "baseline context looks clean", tags=["context"])
```

## 3. Predict

Predictions are recorded as `OutputTransition` and `PredictionPayload`.

```python
predicted = run.predict(input_transition.input_transition_id, max_outcomes=3)
```

Multiple prediction outputs can be created from a single input transition.

## 4. Execute

optagent does not include an executor. External scripts, test runners, benchmark runners, and AI coding tools perform execution.

After execution, pass the results as `ResultPayload`.

```python
result = ResultPayload(
    payload_id="pending",
    target_id="pending",
    status="completed",
    raw_outputs=("raw/bench.txt",),
    metrics={"latency_ms": 1.5},
    matched_prediction_output_id=predicted[0].output_transition_id,
)
```

## 5. Record Results

```python
observed = run.observe(input_transition.input_transition_id, result)
```

`observe` adds an observed output `OutputTransition` and attaches a `ResultPayload` to it.

## 6. Read History

```python
history = run.trace(observed.to_node_id, depth=3)
```

What you can retrieve:

- past node ids
- note payload ids
- input transition ids
- output transition ids
- plan payload ids
- prediction payload ids
- result payload ids
- artifact / raw output / log refs

## 7. Explore with GraphView

For long hypothesis explorations or isolated investigations, create a `GraphView`. View contents are computed at read-time by reachability from `root_node_id`.

```python
view = run.view_create("exp-a", root_node_id=observed.to_node_id)
future_input = run.plan(
    [observed.to_node_id],
    PlanPayload(payload_id="pending", target_id="pending", intent="try variant"),
)
run.predict(future_input.input_transition_id, max_outcomes=3)
```

To integrate exploration results into main, add an `OutputTransition` from a node in main to the `root_node_id` of `exp-a` via `plan` / `observe`. `view_merge` is unnecessary.

## Cut

To invalidate a mistaken plan, cut the input transition.

```python
run.cut(
    input_transition.input_transition_id,
    target_kind="input_transition",
    reason="bad plan",
)
```

To invalidate only a prediction or observed output, cut the output transition.

```python
run.cut(
    predicted[0].output_transition_id,
    target_kind="output_transition",
    reason="bad prediction",
)
```

Cut is not deletion. It appends a `CutPayload`, and active/inactive is computed at read-time.
