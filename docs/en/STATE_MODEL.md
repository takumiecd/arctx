# State Model

`RunGraph` stores append-only dictionaries for:

- `nodes`
- `steps` (public surface: steps)
- `payloads`
- `lanes`
- `work_events`

Each `Step` stores its `input_node_ids` and exactly one `output_node_id`.
There is no persisted `Edge` record in the current schema.

Payload indexes are derived by target: `payloads_by_node` and
`payloads_by_step`, and `payloads_by_lane`.

## Lane DAG and overviews

Lanes form an exploration DAG separate from the Node/Step DAG. Append-only
`lane_linked` events create parent-to-child drill-down links; a child may have
multiple parents and cycle-producing links are rejected. `LanePayload`
(`target_kind="lane"`) carries lane information. `summary` and `purpose` use
the latest payload as their current value, while `question`, `decision`, and
other types accumulate. `lane_overview()` is the collapsed read projection.

Topology indexes are derived from step endpoints:
`steps_by_input_node` and `step_by_output_node`.

Core payloads are generic `NodePayload` / `StepPayload` plus `CutPayload`.
`CutPayload` is the append-only way to invalidate a node or step; the target is
not deleted from storage.
The `diagram` extension provides `DiagramPayload` for diagram/model artifacts.
Its embedded node/edge data may be cyclic because it describes the target
artifact, not the ARCTX `RunGraph`.
Git state is extension state: `GitChangePayload`, branch payloads, and git work
events are registered by `arctx.ext.git`.

Persistence uses `nodes.jsonl`, `steps.jsonl`, `payloads.jsonl`,
`lanes.jsonl`, and `lane_events.jsonl` for JSONL storage, or equivalent
SQLite tables.

`GraphView` / `views` were removed during the 0.3 beta redesign. Old
`views.jsonl` files may remain in existing runs, but new loaders do not import
them into the core graph.
