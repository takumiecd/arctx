# State Model

`RunGraph` は以下を append-only に保持します。

- `nodes: dict[str, Node]`
- `transitions: dict[str, Transition]` — `input_node_ids` (多入力可) と `output_node_id` (必ず 1 つ) を持つ
- `payloads: dict[str, PayloadBase]`
- `views: dict[str, GraphView]`
- `work_sessions`, `work_events`

`Edge` record は廃止済みです。接続情報は `Transition` 自身が保持します。

core payload は汎用 `NodePayload` / `TransitionPayload` と `CutPayload` です。
`GitChangePayload`、branch payload、git 関連 WorkEvent は標準 `git` extension
(`arctx.ext.git`) が登録します。

## 逆引きインデックス（永続化せず、ロード時に再構築）

- `transitions_by_input_node: dict[str, list[str]]` — node → outgoing transition IDs
- `transition_by_output_node: dict[str, str]` — node → incoming transition ID（1 対 1 制約）
- `payloads_by_node`, `payloads_by_transition`

## lookup API

- `transitions_from_node(node_id) -> list[str]`
- `transition_to_node(node_id) -> str | None`
- `transition_inputs(transition_id) -> list[str]`
- `transition_output(transition_id) -> str`
- `payloads_for_node(node_id, *, payload_type=None) -> list[PayloadBase]`
- `payloads_for_transition(transition_id, *, payload_type=None) -> list[PayloadBase]`

## Storage

JSONL: `nodes.jsonl`, `transitions.jsonl`, `payloads.jsonl`, `views.jsonl`,
`work_sessions.jsonl`, `work_events.jsonl`。

`edges.jsonl` は存在しません。SQLite も同じ table 構成。
