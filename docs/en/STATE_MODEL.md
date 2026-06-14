# State Model

`RunGraph` stores append-only dictionaries for:

- `nodes`
- `steps` (public surface: steps)
- `payloads`
- `work_sessions`
- `work_events`

Each `Step` stores its `input_node_ids` and exactly one `output_node_id`.
There is no persisted `Edge` record in the current schema.

Payload indexes are derived by target: `payloads_by_node` and
`payloads_by_step`.

Topology indexes are derived from step endpoints:
`steps_by_input_node` and `step_by_output_node`.

Core payloads are generic `NodePayload` / `StepPayload` plus `CutPayload`.
`CutPayload` is the append-only way to invalidate a node or step; the target is
not deleted from storage.
Git state is extension state: `GitChangePayload`, branch payloads, and git work
events are registered by `arctx.ext.git`.

Persistence uses `nodes.jsonl`, `steps.jsonl`, `payloads.jsonl`,
`work_sessions.jsonl`, and `work_events.jsonl` for JSONL storage, or equivalent
SQLite tables.

`GraphView` / `views` were removed during the 0.3 beta redesign. Old
`views.jsonl` files may remain in existing runs, but new loaders do not import
them into the core graph.
