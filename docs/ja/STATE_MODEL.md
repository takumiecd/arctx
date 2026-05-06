# 状態モデル

## 中心原則

optagent の状態モデルは、次の考え方を中心に置きます。

> 最適化は、状態から action を選び、その実行結果を解釈して、次の状態を作る過程である。

最適化では、実行前に「何をすれば、何が観測されるはずか」を予測します。
実行後には、artifact、log、metric、error などの結果が得られます。
その結果を評価して、予測が当たったか、外れたなら何を学ぶべきかを決めます。

そのため、状態モデルでは以下を分けて扱います。

- 実行前に決める計画
- 実行して得た事実
- 事実から作る解釈
- 解釈にもとづく判断
- 次の action 選択に使う圧縮された作業記憶

この一連の変化を `TransitionRecord` として記録します。

```text
StateNode
  ── TransitionRecord ──>
StateNode
```

より分解すると、次の流れです。

```text
State_t
  -> ActionSpec
  -> ActionResult
  -> DerivedRecords
  -> State_t+1
```

## 基本の切り分け

```text
StateNode:
  点。
  ある時点または未来予測上の状態。

ActionSpec:
  これから実行する action の仕様。
  期待する観測、入力、コスト見積もり、安全条件を持つ。

ActionResult:
  action を実行して出てきた副産物。
  artifact, raw output, logs, metrics, errors など。

TransitionRecord:
  矢印。
  StateNode から StateNode への遷移を、計画・事実・任意の解釈込みで記録する。
```

この分解の目的は、予測と観測を比較できる形で試行を残すことです。
あとから同じ試行を読み返したり、別の evaluator や promotion policy で再評価したりできます。

`ActionSpec` は実行前の計画です。
`ActionResult` は実行後に得られた事実です。
この二つを分けることで、「何を期待していたか」と「実際に何が起きたか」を明確に比較できます。

## Source of Truth / Derived / Working Memory

optagent の中心は、LLM の解釈を保存することではなく、
あとから再解釈できる事実をきれいに保存することです。

```text
source of truth:
  ActionSpec
  ActionResult

derived:
  Observation
  Evidence
  PredictionError
  Decision
  Finding
  StateDelta

working memory:
  StateSnapshot
```

### source of truth

`ActionSpec` と `ActionResult` は source of truth です。

`ActionSpec` は、その時点で何をしようとしていたかを表します。
これは実行後には再現しにくいため、実行前の計画として保存します。

`ActionResult` は、実行して出てきた事実です。
artifact、raw output、stdout、stderr、exit code、timeout、metric、実行時間、環境情報などを含みます。

これらは、後から別の evaluator、別の LLM、別の promotion policy で再評価するための原本です。

### derived

`Observation`、`Evidence`、`PredictionError`、`Decision`、`Finding`、`StateDelta` は derived record です。
source of truth から作る解釈、判断、要約、圧縮です。

derived record は便利ですが、事実そのものではありません。
LLM や evaluator は確率的・設定依存に振る舞うため、同じ raw result から異なる解釈が出ることがあります。
そのため derived record は、必要に応じて作り直せる cache として扱います。

### working memory

`StateSnapshot` は、次の action を選ぶための working memory です。
すべての raw fact を入れる場所ではありません。
過去の事実や derived record から、次の判断に必要なものだけを圧縮して持ちます。

例えば `knowledge` は source of truth ではありません。
過去の `TransitionRecord` と derived record から作った、次の action 選択用の要約です。

## State と Tree

`State` と tree は分けます。

```text
State:
  現在または予測上の状態。

PredictionTree:
  まだ実行していない未来予測。

EvidenceTree:
  実際に実行した遷移の履歴。
```

概念上は以下です。

```text
PredictionTree:
  node = PredictedStateNode
  edge = PlannedTransition

EvidenceTree:
  node = ObservedStateNode
  edge = TransitionRecord
```

`PredictionTree` の edge は「こうすればこうなるはず」という予測です。
`EvidenceTree` の edge は「実際にこうしたらこうなった」という記録です。

`StateNode` 自体には、過去や未来の transition id を直接持たせません。
`StateNode` は状態そのものを表します。
過去へ遡るための index は `EvidenceTree` が持ち、未来を見るための index は `PredictionTree` が持ちます。

現在の state をどの範囲の過去・未来と一緒に読むかは `StateContext` で指定します。

```text
StateNode:
  状態そのもの。

EvidenceTree:
  過去を遡るための incoming / outgoing index を持つ。

PredictionTree:
  未来予測を見るための outgoing / incoming index を持つ。

StateContext:
  現在の StateNode を中心に、どの過去と未来を見るかを指定する。
```

## Tree / Depth / StateNode

tree は depth を持ちます。
agent は node 単体ではなく、depth ごとの layer を見て推論します。

```text
Tree
├── depth 0
│   └── S0: 現在状態
├── depth 1
│   ├── S1: Action A 後の予測状態
│   ├── S2: Action B 後の予測状態
│   └── S3: Action C 後の予測状態
├── depth 2
│   ├── S4: S1 からさらに進んだ予測状態
│   ├── S5: S2 からさらに進んだ予測状態
│   └── S6: S3 からさらに進んだ予測状態
└── depth 3
    └── S7: さらに先の予測状態
```

### depth を見る理由

depth は「何手先の状態か」を表します。

```text
depth 0:
  現在の状態

depth 1:
  次の action を取った直後の状態

depth 2:
  その action が成功または失敗した後に、さらに進んだ状態

depth 3:
  複数の方針を組み合わせた未来状態
```

同じ depth の state node を比較すると、次のような推論ができます。

```text
DepthLayer(depth=1)
├── S1: 調査した後の状態
├── S2: 実装した後の状態
└── S3: benchmark を増やした後の状態

comparison:
├── uncertainty が一番減るのはどれか
├── promotion に近づくのはどれか
├── cost が低いのはどれか
├── risk が高いのはどれか
└── depth 2 以降の展開が良いのはどれか
```

## StateNode

`StateNode` は tree の点です。
中身は、その地点にいると仮定したときの状態です。

```text
StateNode
├── state_id
├── snapshot
├── assumptions
├── confidence
├── status
└── metadata
```

`depth`、`branch_id`、`parent_state_ids`、`transition_id` は `StateNode` の中身ではなく、
tree 側の index や `StateContext` で扱います。
これにより、同じ状態を別の tree view から読むことができます。

### snapshot

`snapshot` は、その node で agent が持っている状態です。

```text
StateSnapshot
├── requirement
├── artifacts
├── knowledge
├── open_questions
├── active_branches
├── predictions
└── budget
```

図にすると次のようになります。

```text
┌──────────────────────────────────────────────┐
│ StateNode S2                                  │
├──────────────────────────────────────────────┤
│ StateSnapshot                                 │
│  requirement: csc_linear_forward latency      │
│  artifacts: baseline only                     │
│  knowledge: small shape は launch-bound       │
│  open_questions: large shape は未説明         │
│  predictions: fused dispatch may help small   │
├──────────────────────────────────────────────┤
│ Node Metadata                                 │
│  assumptions: launch overhead dominates       │
│  confidence: 0.62                             │
│  status: predicted                            │
└──────────────────────────────────────────────┘
```

`StateNode` は、その時点で agent が何を知っているかを表します。
個別の実行 log や benchmark output は node に直接混ぜず、
`TransitionRecord` から辿れる形で保存します。
これにより、状態の比較と実行履歴の検証を分けて扱えます。

## StateContext

`StateContext` は、現在の `StateNode` を tree の中で読むための視点です。
状態そのものではありません。

```text
StateContext
├── current_state_id
├── evidence_tree_id
├── prediction_tree_id
├── current_depth
├── active_branch_ids
├── focus_transition_ids
├── past_depth
├── future_depth
├── include_pruned
└── include_unsafe
```

例えば、agent が `S7` にいるとします。
`S7` の `StateNode` だけを見ると、現在の knowledge や open questions は分かります。
しかし、なぜその状態になったのか、どの失敗を踏んだのか、次にどの未来が予測されているのかは分かりません。

その読み方を指定するのが `StateContext` です。

```text
StateContext:
  current_state_id: S7
  evidence_tree_id: E_run_001
  prediction_tree_id: P_run_001
  past_depth: 3
  future_depth: 2
  focus_transition_ids:
    - T5: fused dispatch implementation
    - T6: large shape benchmark regression
    - P8: scoped dispatch prediction
```

この context があると、agent は「現在状態を中心に、過去 3 step と未来 2 step を読んで判断する」
という推論ができます。

## ActionSpec

`ActionSpec` は、状態から選ばれる「これから何をするか」の仕様です。
実行前に作られ、実行の意図と期待する観測を記録します。

```text
ActionSpec
├── action_id
├── action_type
├── intent
├── inputs
├── expected_observation
├── expected_state_delta
├── estimated_cost
└── safety_policy
```

`ActionSpec` には、実行後に生成された artifact、log、metric は含めません。
それらは `ActionResult` として保存します。
この区別があると、実行前の予測と実行後の事実をそのまま比較できます。

### action_type

最低限、以下に分けます。

```text
InvestigationAction
ImplementationAction
VerificationAction
AnalysisAction
ScopeRefinementAction
```

例:

```text
InvestigationAction:
  profile workload
  run baseline matrix
  inspect dispatch

ImplementationAction:
  generate patch
  edit candidate kernel
  change dispatch condition

VerificationAction:
  run correctness tests
  run benchmark matrix

AnalysisAction:
  explain benchmark regression
  classify failure mode

ScopeRefinementAction:
  restrict dispatch to small batch
  exclude dtype
```

## ActionResult

`ActionResult` は、`ActionSpec` を実行して出てきた副産物です。
成功した場合だけでなく、失敗した場合の error、timeout、partial output も含めます。

```text
ActionResult
├── action_id
├── status
├── artifacts
├── raw_outputs
├── logs
├── metrics
├── errors
├── actual_cost
└── metadata
```

例:

```text
ActionSpec:
  action_type: ImplementationAction
  intent: implement fused dispatch

ActionResult:
  status: completed
  artifacts:
    - artifacts/attempt_0007.patch
  raw_outputs:
    - raw/attempt_0007_tests.txt
    - raw/attempt_0007_benchmark.txt
  metrics:
    small_latency_ms: 8.1
    large_latency_ms: 220.0
```

## TransitionRecord

`TransitionRecord` が矢印です。
一つの試行について、実行前の計画と実行後の事実を必ず残します。
そこから作った観測、証拠、判断、学習、状態差分は derived record として任意に追加します。

```text
TransitionRecord
├── transition_id
├── from_state_id
├── to_state_id
├── action_spec
├── action_result
└── derived_records
```

図にすると、次の関係です。

```text
┌──────────────┐
│ StateNode S0 │
└──────┬───────┘
       │
       │ TransitionRecord T7
       │  ├─ ActionSpec
       │  ├─ ActionResult
       │  └─ DerivedRecords
       │     ├─ Evidence
       │     ├─ PredictionError
       │     ├─ Decision
       │     ├─ Finding
       │     └─ StateDelta
       v
┌──────────────┐
│ StateNode S7 │
└──────────────┘
```

`TransitionRecord` を読めば、次の問いに答えられる必要があります。

- どの状態から始めたのか
- 何をしようとしたのか
- 何が起きると予測していたのか
- 実際には何が起きたのか
- どの raw fact が保存されているのか
- どの derived record が追加されているのか

`Decision` や `Finding` は `TransitionRecord` に直接必須で持たせません。
それらは `ActionResult` から後で作れる解釈です。
必要なら複数の evaluator や LLM が、同じ transition に対して別々の derived record を追加できます。

```text
DerivedRecord
├── derived_id
├── source_transition_id
├── derived_type
│   ├── observation
│   ├── evidence
│   ├── prediction_error
│   ├── decision
│   ├── finding
│   ├── state_delta
│   └── summary
├── payload
├── generator
├── confidence
└── metadata
```

`generator` には、何がその derived record を作ったかを残します。

例:

```text
generator:
  evaluator:benchmark_parser:v1
  promotion_gate:v1
  llm:gpt-5.5:prompt_hash_abc
  human:takumi
```

## PredictionTree

`PredictionTree` は、まだ実行していない未来予測です。

```text
PredictionTree

depth 0   [S0: current state]
             |
             | PlannedTransition P1
             | ActionSpec: profile workload
             v
depth 1   [S1: profile 後の予測状態]

             |
             | PlannedTransition P2
             | ActionSpec: implement fused dispatch
             v
depth 2   [S2: candidate を持つ予測状態]
```

`PredictionTree` の edge は `PlannedTransition` です。

```text
PlannedTransition
├── from_state_id
├── to_predicted_state_id
├── action_spec
├── expected_observation
├── expected_state_delta
├── assumptions
├── confidence
└── estimated_cost
```

ここには `ActionResult` はありません。
まだ実行していないからです。

## EvidenceTree

`EvidenceTree` は、実際に実行した遷移の履歴です。
名前に `Evidence` が入っていますが、source of truth は `ActionSpec` と `ActionResult` です。
`Evidence` は必要に応じて追加される derived record です。

```text
EvidenceTree

depth 0   [S0: observed baseline state]
             |
             | TransitionRecord T1
             | ActionSpec + ActionResult + optional DerivedRecords
             v
depth 1   [S1: observed state after action]

             |
             | TransitionRecord T2
             v
depth 2   [S2: observed state after next action]
```

`EvidenceTree` は append-only です。
過去に実行した遷移を書き換えません。

ただし、枝の merge や shared parent を表現するために、内部実装は graph になっても構いません。
その場合でも、agent が読む view は depth を持つ EvidenceTree として提供します。

## PredictionTree から EvidenceTree への変換

予測段階では、`PlannedTransition` だけがあります。

```text
PredictionTree

S0
 │
 │ PlannedTransition P7
 │  ActionSpec:
 │    implement fused dispatch
 │  expected:
 │    small improves
 │    large neutral
 v
S7_predicted
```

実行後は、`ActionResult` が得られ、
`TransitionRecord` として EvidenceTree に記録されます。
その後、必要に応じて `Evidence` や `Decision` などの derived record を追加します。

```text
EvidenceTree

S0
 │
 │ TransitionRecord T7
 │  ActionSpec:
 │    implement fused dispatch
 │  ActionResult:
 │    patch, test logs, benchmark logs
 │  DerivedRecords:
 │    Evidence:
 │      small +18%, large -8%
 │    PredictionError:
 │      large was not neutral
 │    Decision:
 │      needs_narrower_scope
 │    Finding:
 │      useful only for small batch
 v
S7_observed
```

このとき、`ActionSpec` は変更しません。
実行前の予測は `ActionSpec` に残し、実行後の事実は `ActionResult` に残します。
予測との差分は、必要なら `PredictionError` derived record として保存します。

## 状態遷移の 1 step

1 step は以下のように表します。

```text
StateNode S_t
  -> choose ActionSpec
  -> execute ActionSpec
  -> produce ActionResult
  -> optionally derive Observation / Evidence / PredictionError / Decision / Finding / StateDelta
  -> create StateNode S_t+1
  -> append TransitionRecord
```

数式的には以下です。

```text
ActionSpec_t = policy(StateNode_t)
ActionResult_t = execute(ActionSpec_t)
DerivedRecords_t = derive(ActionSpec_t, ActionResult_t, context)
StateDelta_t = select_state_delta(DerivedRecords_t)
StateNode_t+1 = apply(StateNode_t, StateDelta_t)
TransitionRecord_t = record(
  StateNode_t,
  ActionSpec_t,
  ActionResult_t,
  DerivedRecords_t,
  StateNode_t+1,
)
```

## 遷移の種類

遷移の種類は、`ActionSpec.action_type` によって決まります。

### 調査遷移

不確実性を減らす遷移です。

```text
S0:
  open_questions:
    - bottleneck は launch overhead か memory access か

ActionSpec:
  type: InvestigationAction
  intent: profile workload by shape
  expected_observation:
    - small shape では launch overhead が支配的に見える

ActionResult:
  raw_outputs:
    - profiler output

DerivedRecords:
  Evidence:
    small shape: launch overhead high
    large shape: memory bandwidth high
  StateDelta:
    knowledge += small shape is launch-bound
    open_questions += large shape の memory layout を調べる
    active_branches += branch_launch_overhead_small
    active_branches += branch_memory_layout_large

S1:
  原因候補が分岐した状態
```

### 実装遷移

candidate artifact を作る遷移です。

```text
S0:
  knowledge:
    - small shape は launch-bound

ActionSpec:
  type: ImplementationAction
  intent: implement fused dispatch for small shapes
  expected_observation:
    - small latency improves
    - large latency neutral

ActionResult:
  artifacts:
    - artifacts/attempt_0007.patch
  raw_outputs:
    - tests.txt
    - benchmark.txt

DerivedRecords:
  Evidence:
    correctness: passed
    small speedup: 1.18
    large speedup: 0.92
  PredictionError:
    large latency was not neutral
  Decision:
    needs_narrower_scope
  Finding:
    fused dispatch is promising only for small batch
  StateDelta:
    artifacts += scoped candidate
    knowledge += do not promote broadly for large batch
    active_branches += small batch scope refinement
    pruned_branches += large fused dispatch

S1:
  scoped candidate と新しい finding を持つ状態
```

### 検証遷移

candidate を promotion できるか確認する遷移です。

```text
ActionSpec:
  type: VerificationAction
  intent: run narrowed benchmark matrix
  expected_observation:
    - batch_size<=4 では correctness passed
    - batch_size<=4 では speedup >= 1.05

ActionResult:
  raw_outputs:
    - narrowed_benchmark.txt

DerivedRecords:
  Evidence:
    correctness: passed
    eligible_scope: batch_size<=4
    geometric_mean_speedup: 1.11
    regressions: []
  Decision:
    accepted
  StateDelta:
    incumbent += candidate for batch_size<=4
    open_questions -= narrowed scope verification
```

### 分析遷移

予測と観測がズレたとき、その原因を説明する遷移です。

```text
ActionSpec:
  type: AnalysisAction
  intent: explain large-shape regression

ActionResult:
  logs:
    - benchmark breakdown
    - code inspection notes

DerivedRecords:
  Finding:
    fused path adds overhead when compute dominates
  StateDelta:
    knowledge += avoid fused dispatch for compute-dominant large shapes
    pruned_branches += branch_large_fused_dispatch
```

### 範囲調整遷移

candidate 自体は有望だが、適用範囲が広すぎるときの遷移です。

```text
ActionSpec:
  type: ScopeRefinementAction
  intent: restrict dispatch scope to batch_size<=4

ActionResult:
  artifacts:
    - narrowed dispatch policy

DerivedRecords:
  Evidence:
    eligible_scope: batch_size<=4
    regressions outside scope: excluded
  StateDelta:
    artifacts += candidate with narrowed dispatch policy
    knowledge += scope constraint
```

## 状態更新の対象

`StateDelta` は、`StateNode` に適用される差分です。

```text
StateDelta
├── artifact_changes
├── knowledge_changes
├── open_question_changes
├── branch_changes
├── prediction_changes
└── budget_changes
```

図にすると以下です。

```text
┌────────────────────┐
│ StateNode S_t       │
├────────────────────┤
│ artifacts           │
│ knowledge           │
│ open_questions      │
│ active_branches     │
│ predictions         │
│ budget              │
└─────────┬──────────┘
          │ apply StateDelta
          v
┌────────────────────┐
│ StateNode S_t+1     │
├────────────────────┤
│ artifacts updated   │
│ knowledge updated   │
│ questions updated   │
│ branches updated    │
│ predictions updated │
│ budget updated      │
└────────────────────┘
```

## 不変条件

状態モデルには以下の不変条件を置きます。

1. `Requirement` は run の中で原則固定する。
2. `ActionSpec` は実行後に変更しない。
3. `ActionResult` は実行によって得た副産物を保存する。
4. raw output は保存する。
5. `Observation`、`Evidence`、`Decision`、`Finding` は derived record として扱う。
6. derived record には generator を残す。
7. `Finding` は次の action 選択に使える圧縮知識として保存する。
8. `StateSnapshot` は source of truth ではなく working memory とする。
9. `TransitionRecord` は append-only とする。
10. promotion と learning は分ける。
11. action 実行前に expected observation を持つ。
12. action 実行後に prediction error を評価できるように raw fact を保存する。
13. unsafe な試行は rejected ではなく `unsafe` として分ける。

## 保存形式

最初は JSON / JSONL を正とします。

```text
runs/<run_id>/
├── run.json
├── requirements.json
├── states.jsonl
├── transitions.jsonl
├── derived_records.jsonl
├── findings.jsonl
├── artifacts/
├── raw/
└── reports/
```

`transitions.jsonl` には source of truth を置きます。
`derived_records.jsonl` には、そこから作られた解釈や判断を置きます。
`findings.jsonl` は、次の action 選択で検索しやすいように抜き出した finding index として扱います。

既存実装では `attempts.jsonl` という名前を使っています。
新しいモデルでは、意味としては `transitions.jsonl` に近いです。
移行時は互換性を見ながら名前を決めます。

DB はまだ不要です。
まずは人間と agent が読める file contract を安定させます。

## まとめ

この状態モデルの中心は以下です。

```text
StateNode:
  点。現在または未来予測上の状態。

ActionSpec:
  これから行う action の仕様。結果は持たない。

ActionResult:
  action を実行して出てきた副産物。

TransitionRecord:
  矢印。ActionSpec、ActionResult、任意の DerivedRecord を束ねる。

DerivedRecord:
  ActionSpec と ActionResult から作る解釈、判断、学習、圧縮。

PredictionTree:
  まだ実行していない future StateNode と PlannedTransition の tree。

EvidenceTree:
  実行済み StateNode と TransitionRecord の tree。
```

この形にすると、`State -> Action -> Result -> State` の反復推論を保ちながら、
実行前の予測と実行後の事実を原本として保存し、証拠にもとづく判断や次に使う知識を
derived record として積み上げられます。
