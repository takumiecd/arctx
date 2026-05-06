# プロジェクトの方向性

## 一言でいうと

optagent は、最適化エージェントのための **証拠管理基盤** です。

目的は、汎用エージェントフレームワークを作ることではありません。
コード最適化やカーネル最適化において、各試行を再現可能で比較可能な形に残し、
次の試行に使える知識として蓄積することです。

```text
Requirement
  -> StateNode
      -> TransitionRecord
          -> ActionSpec
          -> ActionResult
          -> Observation
          -> Evidence
          -> PredictionError
          -> Decision
          -> Finding
          -> StateDelta
      -> StateNode
```

最適化試行が次の問いに答えられないなら、optagent としては不十分です。

- なぜその試行をしたのか
- 何を実行したのか
- 何を観測したのか
- どの証拠をもとに判断したのか
- なぜ採用、拒否、範囲縮小、追加検証、危険判定になったのか
- 次の試行に何を学習として残すのか

## 中心に置くもの

中心に置くのは LLM でも MCTS でも ManagerAgent でもありません。
中心に置くのは **PredictionTree / EvidenceTree** です。

`PredictionTree` は、まだ実行していない未来予測です。
`EvidenceTree` は、実際に実行した試行と証拠の履歴です。

`StateNode` は点です。
`TransitionRecord` は矢印です。
`ActionSpec` はその矢印の中に含まれる「これから何をするか」の仕様であり、
実行結果は `ActionResult` として別に残します。

LLM、探索アルゴリズム、planner、heuristic は差し替え可能です。
しかし、証拠、判断、学習結果が残らない最適化は optagent の対象ではありません。

## 作るもの

安定した構成は以下を目指します。

```text
optagent
├── core
│   ├── canonical schema
│   ├── PredictionTree / EvidenceTree
│   ├── PromotionGate inputs/outputs
│   └── StateStore
├── workflows
│   └── hypothesis-test workflow
├── domains
│   ├── kernel
│   └── code
├── execution
│   ├── backend adapters
│   ├── executors
│   ├── evaluators
│   └── sandbox/worktree policy
└── storage
    ├── run directories
    ├── artifacts
    ├── raw outputs
    ├── evidence
    └── findings
```

現在のコードには `v1` や `v2` という歴史的な名前が残っています。
ただし、今後の設計ではそれらをプロダクトの中心概念として扱いません。

## 作らないもの

optagent は以下を目指しません。

- 汎用 chatbot framework
- LangChain 的な general agent framework
- benchmark 付き code generator
- MCTS を主役にした研究デモ
- 生成コードをデフォルトで元ファイルへ直接書き戻すツール

自動 write-back は原則禁止です。
候補は patch、artifact、candidate directory、worktree などに隔離し、
明示的に promotion された後だけ適用を検討します。

## 最初に強くするドメイン

最初に本気で強くするべきドメインは kernel optimization です。

理由は、kernel optimization では以下が自然に必要になるためです。

- dispatch key ごとの適用可否
- shape family ごとの性能
- dtype / device ごとの差
- correctness
- latency
- regression
- narrowed scope
- raw benchmark preservation

これは optagent の EvidenceTree と PromotionGate が最も価値を出しやすい領域です。

## 近い実装方針

1. 日本語の `DIRECTION / STATE_MODEL / AGENT_LOOP` を正本として固める。
2. `core` を canonical schema と storage layer にする。
3. `State`、`PredictionTree`、`EvidenceTree` の責務を明確に分ける。
4. `ActionSpec` を investigation / implementation / verification に分ける。
5. `PromotionGate` を canonical `Decision` を返す形に寄せる。
6. `Finding` を検索する `KnowledgeStore` を作る。
7. kernel domain の最小 workflow を作る。
