# State Model

This document describes the state model targeted in STAG 0.1 alpha.

In 0.1 alpha, model refinement takes priority over backward compatibility. The old `StateNode` / `ExecutionPlan` / `PredictionPlan` / `ObservedTransition` / `PredictedTransition` / `ActionResult` forms are deprecated in favor of run-wide graph records and payloads.

## Overview

```text
RunHandle
  └── run_graph: RunGraph

RunGraph
  ├── nodes: dict[str, Node]
  ├── input_transitions: dict[str, InputTransition]
  ├── output_transitions: dict[str, OutputTransition]
  ├── payloads: dict[str, Payload]
  ├── views: dict[str, GraphView]
  ├── input_transitions_from_node
  ├── output_transitions_from_it
  ├── output_transitions_to_node
  ├── payloads_by_node
  ├── payloads_by_input_transition
  └── payloads_by_output_transition

GraphView
  ├── view_id: str
  ├── name: str
  ├── root_node_id: str   ← single root node
  └── metadata
```

`RunGraph` is the DAG for the entire run. `Node` / `InputTransition` / `OutputTransition` / `Payload` IDs are globally unique within a run.

`GraphView` is a subset of `RunGraph`. `main` is just one special `GraphView`.

## Append-only

`RunGraph` is append-only. Once added, `Node` / `InputTransition` / `OutputTransition` / `Payload` are never deleted.

State changes, cancellation, invalidation, comparisons, and interpretation updates are expressed by adding new records and payloads.

- Adding a plan: create `InputTransition` and `PlanPayload`
- Adding a node memo: create `NotePayload`
- Adding a prediction: create `OutputTransition` and `PredictionPayload`
- Adding an execution result: create `OutputTransition` and `ResultPayload`
- Invalidating a plan: attach `CutPayload` to the `InputTransition`
- Invalidating a prediction/result: attach `CutPayload` to the `OutputTransition`
- View contents: computed at read-time by reachability from `root_node_id`

Read-time views, active/inactive determination, and trace display decide "what should be visible now." Stored records are never destroyed to rewrite the past.

## Input Side and Output Side

STAG separates transitions into input side and output side.

```text
input nodes
  -> InputTransition + PlanPayload
  -> OutputTransition + PredictionPayload | ResultPayload
  -> output node
```

The input side allows multiple nodes. The output side is one node per output transition.

```text
n_0000, n_0003
  -> it_0001
  -> ot_0001
  -> n_0004
```

This separation allows plan information to be attached to the input side and predictions/results to the output side.

## Why GraphView

If parent Dag / child Dag each have their own `nodes` and `transitions`, semantics break when the same ID is used across different Dags. Furthermore, cross-references where a parent transition points to a child node make indexing and storage ambiguous.

Therefore, record instances are consolidated in `RunGraph`. Experiments and hypothesis explorations view subsets via `reachable_from` from a `root_node_id` without copying records.

The same node can be visible from multiple views via `reachable_from`. View integration is simply a matter of adding an edge on the graph via normal `plan` / `observe` — no dedicated merge operation is needed.

## Pure Graph Records

### Node

`Node` is a pure graph node.

```python
Node(node_id="n_<opaque>", metadata={})
```

Nodes do not directly hold state contents. Necessary information is attached as payloads to nodes / input transitions / output transitions.

Lightweight memos can be attached to nodes as `NotePayload`. These are not sources of truth — they are context, observations, TODOs, and supplementary notes left by humans or evaluators.

### InputTransition

`InputTransition` is the entry point for an operation starting from multiple input nodes.

```python
InputTransition(
    input_transition_id="it_<opaque>",
    input_node_ids=("n_<opaque>", "n_<opaque>"),
)
```

`InputTransition` holds only the graph skeleton. Plan information such as intent, input parameters, constraints, and assumptions is attached as `PlanPayload`.

### OutputTransition

`OutputTransition` is an edge from an `InputTransition` to a single output node.

```python
OutputTransition(
    output_transition_id="ot_<opaque>",
    input_transition_id="it_<opaque>",
    to_node_id="n_<opaque>",
)
```

The meaning of the output is determined by the attached payload.

- `PredictionPayload`: predicted outcome before execution
- `ResultPayload`: actual outcome that occurred

`PredictionPayload` and `ResultPayload` cannot coexist on the same `OutputTransition` (rejected at `attach_payload` time).

Multiple prediction outputs and multiple observed outputs can be created from a single `InputTransition`. For operations where results vary probabilistically, multiple observed outputs can be recorded side by side under the same plan.

## Payload

Domain data is not embedded in graph records but attached as payloads. Multiple payloads can be attached to a single target.

Payloads have `target_kind` and `target_id`.

```python
PlanPayload(
    payload_id="pl_0001",
    target_kind="input_transition",
    target_id="it_0001",
    ...
)
```

`target_kind` is one of:

- `node`
- `input_transition`
- `output_transition`

The minimum payload set for 0.1 is:

- `NotePayload`
- `PlanPayload`
- `PredictionPayload`
- `ResultPayload`
- `CutPayload`

### NotePayload

A lightweight memo attached to a `Node`.

Contains:

- text
- author
- tags
- metadata

`NotePayload` is not a source of truth. It is used to leave supplementary notes and short human-facing memos tied to nodes, not to save state as giant snapshots.

### PlanPayload

Plan information attached to an `InputTransition`.

Contains:

- intent
- action type
- inputs
- constraints
- assumptions
- safety policy
- metadata

### PredictionPayload

Predicted outcome attached to a prediction output.

Contains:

- predicted artifacts
- predicted metrics
- rationale
- probability: estimated probability this outcome occurs (0–1 / None)
- confidence: how confident the predictor is in that estimate (None allowed)
- predictor
- metadata

`probability` is the likelihood of the outcome; `confidence` is the reliability of the prediction. They are distinct concepts.

### ResultPayload

Execution result attached to an observed output.

Contains:

- artifacts
- raw outputs
- logs
- metrics
- errors
- actual cost
- matched_prediction_output_id
- metadata

The correspondence between prediction and observation is expressed via `ResultPayload.matched_prediction_output_id`, not via `MatchPayload`.

### CutPayload

`CutPayload` can be attached to an `InputTransition` or `OutputTransition`.

When attached to an `InputTransition`, the entire plan is treated as inactive. Predictions and observed outputs from that input are also rendered inactive at read-time.

When attached to an `OutputTransition`, only that output is treated as inactive. Other outputs from the same input transition remain.

`CutPayload` is not attached to nodes themselves. Since nodes can be referenced from multiple inputs/outputs, cut targets are limited to transitions. Payloads attached to nodes are limited to non-destructive supplementary information like `NotePayload`.

## GraphView

`GraphView` is a label that holds only a `root_node_id`. View contents (node_ids / input_transition_ids / output_transition_ids / payload_ids) are not persisted — they are computed at read-time via `RunGraph.reachable_from(root_node_id)`.

```text
main
  root_node_id: n_0000
  → reachable: n_0000, n_0001, it_0001, ot_0001, ...

exp-a
  root_node_id: n_0001
  → reachable: n_0001, n_0100, it_0100, ot_0100, ...
```

To "integrate a view", simply add one `OutputTransition` from any node in main to the `root_node_id` of `exp-a`. This is accomplished through normal `plan` / `observe` — `view_merge` is unnecessary.

`GraphView` itself does not distinguish between prediction and observed. Both are records on the same `RunGraph`, differentiated by payload type. To trace only observed history, use `run.trace`. To see outcomes including predictions, use `run.outcomes`.

## Trace

`run.trace(node_id, ...)` traverses past observed history from the specified node via backward BFS.

- Collects all active incoming OTs that have `ResultPayload`. Inactive OTs (rewound) are not traversed.
- From each observed OT, moves to its `InputTransition` and enqueues **all nodes** listed in `input_node_ids`. Even multi-input ITs (merge nodes) correctly collect all ancestors.
- Already-visited nodes are skipped without duplication.
- `depth` is the number of backward steps (`None` for all ancestors).
- Collection fields of `TraceContext` are returned as ascending sorted tuples. `artifact_refs` is a deduplicated tuple preserving appearance order.

## Cut

`cut` appends a `CutPayload`.

Key points:

- Nodes / input transitions / output transitions / payloads are not deleted
- Active / inactive is computed at read-time
- New outputs cannot be created from cut input transitions
- Cut output transitions are treated as inactive in trace and view

### is_inactive_input_transition Determination Rules

`is_inactive_input_transition(graph, it_id)` determines an IT as inactive if either condition applies:

1. **Direct cut**: `CutPayload(target_kind="input_transition")` is attached to that IT.
2. **Input node is inactive**: Any of the IT's `input_node_ids` is in `inactive_node_ids` (i.e., an upstream OT was cut, rendering the input node inactive).

`predict` and `observe` raise `ValueError` for inactive ITs, refusing to add new output transitions.

## Storage

JSONL storage only handles the run graph format.

```text
run.json
graph.json
views.jsonl
nodes.jsonl
input_transitions.jsonl
output_transitions.jsonl
payloads.jsonl
```

Storage also assumes append-only semantics. Logical cancellation and invalidation are expressed through additional records/payloads and read-time computation, not through deletion of existing lines.

Migration from old formats is not supported in 0.1 alpha.
