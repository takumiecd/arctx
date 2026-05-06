# プロジェクトの方向性

## 一言でいうと

optagent は、問題解決や最適化の過程で出てくる **事実と構造化メモを整理し、
人間・AI・自動化が同じ文脈を共有するための基盤** です。

目的は、汎用エージェントフレームワークを作ることではありません。
コード最適化やカーネル最適化に限らず、調査、実験、実装、検証で得た事実を
再解釈できる形で残し、次の行動に使える作業文脈として整理することです。

```text
Requirement
  -> StateNode
      -> TransitionRecord
          -> ActionSpec
          -> ActionResult
          -> DerivedRecords
      -> StateNode
```

最適化試行が次の問いに答えられないなら、optagent としては不十分です。

- なぜその試行をしたのか
- 何を実行したのか
- 実行して何が出たのか
- どの raw output / artifact / metric を残したのか
- その事実からどのような解釈や判断を作ったのか
- なぜ採用、拒否、範囲縮小、追加検証、危険判定になったのか
- 次の試行に何を学習として残すのか

ここでいう derived record は、事実に対する構造化メモです。
人間が書く実験ノート、LLM が作る要約、evaluator が作る evidence、promotion gate が作る decision は、
すべて同じ「事実から作ったメモ」として扱います。
形式を揃えることで、人間も AI も同じ文脈を読み直せます。

## 中心に置くもの

中心に置くのは LLM でも MCTS でも ManagerAgent でもありません。
中心に置くのは **PredictionTree / EvidenceTree** です。

`PredictionTree` は、まだ実行していない未来予測です。
`EvidenceTree` は、実際に実行した遷移と source-of-truth facts の履歴です。

`StateNode` は点です。
`TransitionRecord` は矢印です。
`ActionSpec` は実行前の計画です。
`ActionResult` は実行後に得られた artifact、log、metric、error などの結果です。

optagent で最も重視するのは、再解釈できる事実をきれいに残すことです。
`ActionSpec` と `ActionResult` は source of truth として扱います。
`Observation`、`Evidence`、`Decision`、`Finding`、`StateDelta` は、その事実から作る derived record です。

derived record は重要ですが、事実そのものではありません。
LLM、evaluator、promotion policy、人間の判断によって後から作り直せる解釈や圧縮です。

```text
source of truth:
  ActionSpec + ActionResult

derived interpretation:
  Observation / Evidence / PredictionError / Decision / Finding / StateDelta

working memory:
  StateSnapshot
```

この分解により、各試行について「何を期待していたか」「実際に何が起きたか」を残し、
あとから別の evaluator や LLM で再評価できます。

LLM、探索アルゴリズム、planner、heuristic は差し替え可能です。
しかし、証拠、判断、学習結果が残らない最適化は optagent の対象ではありません。

## 作るもの

安定した構成は以下を目指します。

```text
optagent
├── core
│   ├── canonical schema
│   ├── StateNode / ActionSpec / ActionResult / TransitionRecord
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
├── storage
│   ├── run directories
│   ├── artifacts
│   ├── raw outputs
│   ├── derived records
│   └── finding indexes
└── legacy
    ├── previous core
    ├── v1
    └── v2
```

旧実装は `legacy` に退避します。
`v1` や `v2` は参考実装として残しますが、今後の設計ではプロダクトの中心概念として扱いません。

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
