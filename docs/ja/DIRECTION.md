# プロジェクトの方向性

optagent は、問題解決や最適化の過程を構造化して保存するためのライブラリです。

コード最適化、カーネル最適化、実験、調査では、単に「最終的なコード」だけでなく、
途中で何を試し、何が起き、何を学んだかが重要になります。
optagent は、その過程をあとから読み返せる形で残すことを目的にしています。

## 目的

optagent が扱う中心情報は次の 4 つです。

- plan: 何をするつもりだったか
- prediction: 何が起きると考えていたか
- result: 実際に何が起きたか
- derived record: その結果から何を解釈したか

この情報を残すことで、次の問いに答えられるようにします。

- なぜその試行をしたのか
- 実行前に何を期待していたのか
- 実行して何が出たのか
- どの artifact、log、metric が根拠なのか
- 予測と実測はどれくらい合っていたのか
- 採用、拒否、追加調査の判断は何に基づくのか
- 次の試行で何を避けるべきか

## 中心モデル

optagent は、予測と実測を分けて保存します。

```text
PredictionDAG:
  まだ実行していない未来の候補。

TraceDAG:
  実際に起きたことの履歴。
```

基本的な流れは次の通りです。

```text
ObservedState
  -> ExecutionPlan
  -> PredictedTransition
  -> ActionResult
  -> ObservedTransition
  -> ObservedState
```

`PredictionDAG` では、1 つの plan から複数の未来 outcome を考えられます。
`TraceDAG` では、実際に起きた outcome を source of truth として保存します。

## optagent がやること

optagent は次の機能を提供します。

- run を作る
- observed state と predicted state を管理する
- plan を作る
- 未来 outcome を予測として保存する
- 実行結果を trace に保存する
- 予測と実測の対応を保存する
- derived record を実行履歴に紐づける
- 過去の履歴を辿れるようにする

現在の core 実装は in-memory です。
永続化、CLI、domain-specific workflow は今後追加します。

## optagent がやらないこと

optagent は、現時点では次のものではありません。

- 汎用 chatbot framework
- LangChain 的な general agent framework
- benchmark 付き code generator
- executor を内蔵した自動最適化ツール
- 生成コードを自動で元ファイルに書き戻すツール

executor、planner、predictor、LLM、benchmark runner は外側から接続します。
optagent の core は、それらが生み出す plan、prediction、result、derived record を保存する基盤です。

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

これらは、optagent の `TraceDAG` と `DerivedRecord` が価値を出しやすい領域です。

## 近い実装予定

1. in-memory API を安定させる
2. JSONL / run directory storage を追加する
3. CLI から run を作成、更新、参照できるようにする
4. executor / evaluator の protocol を整える
5. code optimization の小さな workflow を作る
6. kernel optimization の workflow を作る

## ドキュメント

- [API](API.md): Python API の使い方
- [状態モデル](STATE_MODEL.md): PredictionDAG / TraceDAG の考え方
- [問題解決ループ](AGENT_LOOP.md): optagent を使った作業サイクル
