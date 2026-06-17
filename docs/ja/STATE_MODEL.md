# State Model

`RunGraph` は次の append-only な辞書を保持します:

- `nodes`
- `steps`（公開サーフェス: steps）
- `payloads`
- `work_sessions`
- `work_events`

各 `Step` は `input_node_ids` と、ちょうど 1 つの `output_node_id` を保持します。
現行スキーマには永続化された `Edge` record はありません。

Payload のインデックスは target から導出されます: `payloads_by_node` と
`payloads_by_step`。

トポロジのインデックスは step の端点から導出されます:
`steps_by_input_node` と `step_by_output_node`。

コア payload は汎用の `NodePayload` / `StepPayload` に加えて `CutPayload` です。
`CutPayload` は node または step を無効化する append-only な手段で、対象は
ストレージから削除されません。
`diagram` extension は図・モデル artifact 用の `DiagramPayload` を提供します。
中に持つ node/edge は対象 artifact の構造であり、ARCTX の `RunGraph` ではないため
循環していても構いません。
Git の状態は extension の状態です: `GitChangePayload`、branch payload、git の
work event は `arctx.ext.git` が登録します。

永続化は JSONL ストレージでは `nodes.jsonl`, `steps.jsonl`, `payloads.jsonl`,
`work_sessions.jsonl`, `work_events.jsonl` を、あるいは同等の SQLite テーブルを
使います。

`GraphView` / `views` は 0.3 beta の再設計で削除されました。既存の run には
古い `views.jsonl` が残る場合がありますが、新しいローダーはそれらをコアグラフへ
読み込みません。
