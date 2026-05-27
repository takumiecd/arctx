# State Model

`RunGraph` stores append-only dictionaries for:

- `nodes`
- `transitions`
- `payloads`
- `views`
- `work_sessions`
- `work_events`

Each `Transition` stores its `input_node_ids` and exactly one `output_node_id`.
There is no persisted `Edge` record in the current schema.

Payload indexes are derived by target: `payloads_by_node` and
`payloads_by_transition`.

Topology indexes are derived from transition endpoints:
`transitions_by_input_node` and `transition_by_output_node`.

Core payloads are generic `NodePayload` / `TransitionPayload` plus `CutPayload`.
Git state is extension state: `GitChangePayload`, branch payloads, and git work
events are registered by `arctx.ext.git`.

Persistence uses `nodes.jsonl`, `transitions.jsonl`, `payloads.jsonl`,
`views.jsonl`, `work_sessions.jsonl`, and `work_events.jsonl` for JSONL storage,
or equivalent SQLite tables.
