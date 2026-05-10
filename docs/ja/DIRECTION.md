# プロジェクトの方向性

optagent は、問題解決や最適化の過程を構造化して保存するためのライブラリです。

コード最適化、カーネル最適化、実験、調査では、単に「最終的なコード」だけでなく、途中で何を試し、何が起き、何を学んだかが重要になります。optagent は、その過程をあとから読み返せる形で残します。

## 0.1 Alpha 方針

この段階では後方互換を優先しません。モデルが弱いまま API を固定するより、破壊的変更を許容して core を単純に保ちます。

明示的な方針:

- package version は `0.1.0` のまま進める
- 旧 API との shim は原則追加しない
- 旧 storage schema の migration は原則追加しない
- docs は 0.1 の target model を固定するために使う
- テストは現在の仕様を固定するために使う

## 中心モデル

optagent は、pure な graph record と domain payload を分けます。

```text
Node / InputTransition / OutputTransition
  = graph の骨格

NotePayload / PlanPayload / PredictionPayload / ResultPayload / CutPayload
  = graph に attach される意味
```

run 全体の DAG は `RunGraph` です。隔離した仮説展開は別の record 空間を持つ child Dag ではなく、`RunGraph` が管理する `GraphView` として表します。`GraphView` は `root_node_id` を起点に read-time の reachability で中身が決まるラベルです。membership を保存しません。

`InputTransition` は複数 input node を受け取ります。plan の intent、制約、入力パラメータなどは `PlanPayload` として input transition に attach します。

`OutputTransition` は input transition から 1 つの output node に到達します。prediction は `PredictionPayload`、実測は `ResultPayload` として output transition に attach します。

node には軽いメモとして `NotePayload` を attach できます。

`RunGraph` は append-only です。一度追加した node / input transition / output transition / payload は削除せず、取り消しや無効化は `CutPayload` と read-time 計算で表します。

## optagent がやること

- run を作る
- `RunGraph` と `GraphView` を管理する
- node に軽いメモを `NotePayload` として保存する
- 複数 input node から `InputTransition` を作る
- plan 情報を `PlanPayload` として保存する
- prediction output と `PredictionPayload` を保存する
- observed output と `ResultPayload` を保存する
- cut を append-only cut として保存する
- `GraphView` を作成・表示する
- JSONL run directory に保存・読み込みする

## optagent がやらないこと

optagent は、現時点では次のものではありません。

- 汎用 chatbot framework
- LangChain 的な general agent framework
- benchmark 付き code generator
- executor を内蔵した自動最適化ツール
- 生成コードを自動で元ファイルに書き戻すツール

executor、planner、predictor、LLM、benchmark runner は外側から接続します。core は、それらが生み出す plan、prediction、result を保存する基盤です。

## 最初に強くする領域

最初に強くする領域は、コード最適化とカーネル最適化です。

特にカーネル最適化では、次の情報を残す必要があります。

- shape family ごとの性能
- dtype / device ごとの差
- correctness
- latency
- regression
- 適用できる dispatch scope
- raw benchmark output

これらは `PredictionPayload` と `ResultPayload` が価値を出しやすい領域です。

## 実装済みのコア機能

1. `RunGraph` + `GraphView` + `InputTransition` / `OutputTransition` モデル
2. `NotePayload` / `PlanPayload` / `PredictionPayload` / `ResultPayload` / `CutPayload` の 5 payload
3. CLI コマンド全セット (`init` / `plan` / `predict` / `observe` / `note` / `cut` / `trace` / `outcomes` / `show` / `reachable` / `view` / `dump` / `guide` / `list` / `current` / `use`)
4. `optagent dump --format outline|mermaid` による run 全体のレンダリング
5. JSONL ストレージ (`run.json` / `graph.json` / `nodes.jsonl` / `input_transitions.jsonl` / `output_transitions.jsonl` / `payloads.jsonl` / `views.jsonl`)

## 今後の方向性

- executor / evaluator の protocol 整備
- domains (code / kernel) の具体化
- search (beam / greedy / MCTS) の接続

## ドキュメント

- [状態モデル](STATE_MODEL.md)
- [API](API.md)
- [CLI](CLI.md)
- [問題解決ループ](AGENT_LOOP.md)
