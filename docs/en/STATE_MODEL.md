# State Model

`RunGraph` stores append-only dictionaries for:

- `nodes`
- `transitions`
- `edges`
- `payloads`
- `views`
- `work_sessions`
- `work_events`

Edges connect different record kinds only. Same-kind edges are rejected.

Payload indexes are derived by target: `payloads_by_node` and
`payloads_by_transition`.

Topology indexes are derived from edges: `outgoing_edges` and `incoming_edges`.

Persistence uses `nodes.jsonl`, `transitions.jsonl`, `edges.jsonl`,
`payloads.jsonl`, `views.jsonl`, `work_sessions.jsonl`, and `work_events.jsonl`
for JSONL storage, or equivalent SQLite tables.
