# API

基本形:

```python
transition = run.plan([node_id], PlanPayload("pending", "pending", "try"))
predicted_nodes = run.predict(transition.transition_id, max_outcomes=2)
observed_node = run.observe(
    transition.transition_id,
    ResultPayload("pending", "pending", "completed"),
)
```

`plan` は Transition、`node -> transition` edge、PlanPayload を作ります。
`predict` は predicted output node、`transition -> node` edge、PredictionPayload
を作ります。`observe` は observed output node、edge、ResultPayload を作ります。

`cut(target_kind="node" | "transition")` は CutPayload を append します。
