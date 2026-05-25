# Simple DAG Redesign Plan

この branch の canonical design は次の形です。

```text
Node -> Transition -> Node -> Transition -> Node
```

## Record

- `Node`: 状態や地点。
- `Transition`: 作業ステップ。
- `Edge`: `node -> transition` または `transition -> node` の接続。
- `Payload`: 意味情報。
- `WorkSession` / `WorkEvent`: user と work session 単位の作業履歴。

## Payload

Graph record は構造だけを持ちます。意味は payload で付けます。

- `PlanPayload`: 何をするつもりか。
- `PredictionPayload`: どうなると予測したか。
- `ResultPayload`: 実際にどうなったか。
- `GitChangePayload`: Git commit / diff。
- `NotePayload`: node へのメモ。
- `CutPayload`: append-only な無効化。

## Append Batch

並列 worker は、既存 record を変更せず、新規 record を batch append します。

batch に含めるもの:

- new nodes
- new transitions
- new edges
- new payloads
- work session
- work events

SQLite storage は `append_batch` を持ち、JSONL storage は全体 save fallback を使えます。

## CLI

ユーザーに見せる主要 ID は `node_id` と `transition_id` です。

- `stag plan --input-node <node_id>` returns `transition`.
- `stag predict <transition_id>` returns output `nodes`.
- `stag observe <transition_id>` returns observed output `node`.
- `stag cut --node` / `stag cut --transition`.
- `stag outcomes <transition_id>`.
- `stag show --transition <transition_id> --outputs`.
- `stag git start <transition_id>`.

## UI Direction

TUI / UI は record の ID を前面に出しすぎず、DAG を図として表示します。
focus した node または transition の payload を詳細 pane に出します。
