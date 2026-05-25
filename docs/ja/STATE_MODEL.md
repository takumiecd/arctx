# State Model

`RunGraph` は以下を append-only に保持します。

- `nodes`
- `transitions`
- `edges`
- `payloads`
- `views`
- `work_sessions`
- `work_events`

Edge は異なる種類の record だけを接続します。同種同士の edge は拒否します。

payload index は `payloads_by_node` と `payloads_by_transition` です。
topology index は `outgoing_edges` と `incoming_edges` です。

JSONL storage は `nodes.jsonl`, `transitions.jsonl`, `edges.jsonl`,
`payloads.jsonl`, `views.jsonl`, `work_sessions.jsonl`, `work_events.jsonl`
を使います。SQLite も同じ record 種別の table を使います。
