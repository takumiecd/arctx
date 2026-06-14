# State Model

Phase 1 の実装では、外向きの用語と内部名が一部ずれています。

外向き:

- `Node`
- `Step`
- `Payload`

内部実装:

- `Node`
- `Step`
- `Payload`

`Step` は現行コード上の `Step` に対応します。

## RunGraph

`RunGraph` は以下を append-only に保持します。

- `nodes: dict[str, Node]`
- `steps: dict[str, Step]`
- `payloads: dict[str, PayloadBase]`
- `work_sessions`
- `work_events`

Phase 1 の途中で `GraphView` / `views` は core model から削除しました。

## Step as Step

内部 `Step` は次の制約を持ちます。

- `input_node_ids`: 1 つ以上の入力 Node。
- `output_node_id`: 必ず 1 つの出力 Node。
- fan-out は同じ入力 Node から複数の Step を作ることで表す。
- join は複数入力の Step で表す。

外向きJSONでは、Phase 1 の新CLIは `kind: "step"` を返します。ただし互換のため、内部IDや一部field名には `step_id` が残る場合があります。

## Payload

Payload は Node / Step に付く意味情報です。

現行内部の `target_kind` は以下です。

- Node payload: `target_kind="node"`
- Step payload: `target_kind="step"`

Phase 2 で内部名を変更する場合、`target_kind="step"` への移行を検討します。

## Cut

Cut は `CutPayload` として保存されます。

削除ではありません。read-time に active / inactive を計算します。

## Storage

Phase 1 では既存schemaを維持します。

- `nodes.jsonl`
- `steps.jsonl`
- `payloads.jsonl`
- `work_sessions.jsonl`
- `work_events.jsonl`

旧 run に `views.jsonl` が残っていても、新しい loader は core graph には取り込みません。

Phase 2 で `steps.jsonl` を `steps.jsonl` に変えるかどうかを決めます。
