# optagent

optagent は、問題解決や最適化の過程で出てくる **事実と構造化メモを整理し、
人間・AI・自動化が同じ文脈を共有するための基盤** です。

中心にあるのは、AI エージェントそのものではありません。
何を実行したのか、何が起きたのか、その事実から何をメモしたのかを、
あとから読み返せる形で残すことです。

中心に置くのは、LLM や探索アルゴリズムではなく PredictionDAG / TraceDAG です。

```text
Requirement
  -> StateNode
      -> Plan
      -> ObservedTransition
          -> ActionResult
          -> DerivedRecords
      -> StateNode
```

`Plan` と `ActionResult` は事実の原本です。
`DerivedRecord` は、その事実に対する構造化メモです。
`StateSnapshot` は、次の action を選ぶための作業メモです。

## 現在の正本ドキュメント

まず日本語版を正として固めています。

- [プロジェクトの方向性](docs/ja/DIRECTION.md)
- [状態モデル](docs/ja/STATE_MODEL.md)
- [API 仕様ドラフト](docs/ja/API.md)
- [エージェントの思考ループ](docs/ja/AGENT_LOOP.md)

古い設計メモや実験的な計画資料は [docs/archive/](docs/archive/README.md) に退避しています。

## コード構成

現在は、旧実装を参考用の `legacy` に退避し、新しい状態モデルを前提に作り直しています。

```text
src/optagent
├── core/       # StateNode, Plan, ActionResult, Transition, DerivedRecord
├── workflows/  # 状態遷移を回す workflow
├── domains/    # kernel / code などの domain plugin
├── execution/  # executor, evaluator, sandbox policy
├── search/     # greedy, beam, mcts などの search policy
├── storage/    # run directory / JSONL などの永続化
└── legacy/     # 旧 core / v1 / v2 実装
```

新規実装では `optagent.v1` / `optagent.v2` を public API として扱いません。
旧コードを参照する場合は `optagent.legacy` 以下を見ます。

## 開発

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q
```

## License

MIT
