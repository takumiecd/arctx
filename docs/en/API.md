# API

Core API shape:

```python
transition = run.plan([node_id], PlanPayload("pending", "pending", "try"))
predicted_nodes = run.predict(transition.transition_id, max_outcomes=2)
observed_node = run.observe(
    transition.transition_id,
    ResultPayload("pending", "pending", "completed"),
)
```

`plan` creates a `Transition`, `node -> transition` edges, and a `PlanPayload`.
`predict` creates predicted output `Node` records, `transition -> node` edges,
and `PredictionPayload` records on the transition. `observe` creates an observed
output `Node`, a `transition -> node` edge, and a `ResultPayload` on the
transition.

`cut(target_kind="node" | "transition")` appends a `CutPayload`.
