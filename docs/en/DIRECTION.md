# Project Direction

optagent is a library for structuring and saving the process of problem-solving and optimization.

In code optimization, kernel optimization, experiments, and investigation, it is not just the "final code" that matters — what you tried along the way, what happened, and what you learned are equally important. optagent preserves that process in a form that can be read back later.

## 0.1 Alpha Policy

At this stage, backward compatibility is not prioritized. Rather than fixing the API while the model is still weak, we accept breaking changes to keep the core simple.

Explicit policies:

- Package version stays at `0.1.0`
- No compatibility shims for old APIs in principle
- No migration for old storage schemas in principle
- Docs are used to pin the 0.1 target model
- Tests are used to pin the current specification

## Core Model

optagent separates pure graph records from domain payloads.

```text
Node / InputTransition / OutputTransition
  = skeleton of the graph

NotePayload / PlanPayload / PredictionPayload / ResultPayload / CutPayload
  = meaning attached to the graph
```

The DAG for an entire run is `RunGraph`. Isolated hypothesis explorations are represented not as child Dags with separate record spaces, but as `GraphView` managed by `RunGraph`. `GraphView` is a label whose contents are determined at read-time by reachability from a `root_node_id`. Membership is not persisted.

`InputTransition` accepts multiple input nodes. Plan intent, constraints, input parameters, etc. are attached to input transitions as `PlanPayload`.

`OutputTransition` goes from an input transition to a single output node. Predictions are attached as `PredictionPayload` and observations as `ResultPayload` on output transitions.

Lightweight memos can be attached to nodes as `NotePayload`.

`RunGraph` is append-only. Once added, nodes / input transitions / output transitions / payloads are never deleted. Cancellation and invalidation are expressed through `CutPayload` and read-time computation.

## What optagent Does

- Create a run
- Manage `RunGraph` and `GraphView`
- Save lightweight memos on nodes as `NotePayload`
- Create `InputTransition` from multiple input nodes
- Save plan information as `PlanPayload`
- Save prediction outputs and `PredictionPayload`
- Save observed outputs and `ResultPayload`
- Save cuts as append-only cuts
- Create and display `GraphView`
- Save to and load from JSONL run directories

## What optagent Does Not Do

optagent is not, at this time:

- A general-purpose chatbot framework
- A LangChain-style general agent framework
- A code generator with built-in benchmarks
- An auto-optimization tool with a built-in executor
- A tool that automatically writes generated code back to source files

Executors, planners, predictors, LLMs, and benchmark runners connect from the outside. The core is the foundation that stores the plans, predictions, and results they produce.

## Initial Focus Areas

The initial focus areas are code optimization and kernel optimization.

In kernel optimization in particular, the following information needs to be preserved:

- Performance per shape family
- Differences by dtype / device
- Correctness
- Latency
- Regression
- Applicable dispatch scope
- Raw benchmark output

These are areas where `PredictionPayload` and `ResultPayload` shine.

## Near-term Implementation Plans

1. Solidify `RunGraph` + `GraphView` + input/output transition model as 0.1
2. Align CLI and JSONL storage specs with documentation
3. Organize payloads into `NotePayload` / `PlanPayload` / `PredictionPayload` / `ResultPayload` / `CutPayload`
4. Materialize `GraphView` workflow creation and display
5. Establish executor / evaluator protocols

## Documentation

- [State Model](STATE_MODEL.md)
- [API](API.md)
- [CLI](CLI.md)
- [Problem-Solving Loop](AGENT_LOOP.md)
