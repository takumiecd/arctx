# 状態モデル

## 中心原則

optagent の状態モデルは、次の考え方を中心に置きます。

> 最適化は、状態から action を選び、その実行結果を解釈して、次の状態を作る過程である。

ここで重要なのは、`Action` に結果を書き込まないことです。

`Action` は「これから何をするか」という仕様です。
実行して出てきた副産物は `ActionResult` に置きます。
予測、観測、証拠、判断、状態差分をまとめたものを `TransitionRecord` として扱います。

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
  -> Observation
  -> Evidence
  -> PredictionError
  -> Decision
  -> Finding
  -> StateDelta
  -> State_t+1
```

## 基本の切り分け

```text
StateNode:
  点。
  ある時点または未来予測上の状態。

ActionSpec:
  これから実行する action の仕様。
  実行結果は持たない。

ActionResult:
  action を実行して出てきた副産物。
  artifact, raw output, logs, metrics, errors など。

TransitionRecord:
  矢印。
  StateNode から StateNode への遷移を、予測・結果・証拠・判断込みで記録する。
```

この分解により、`ActionSpec` は immutable にできます。
実行後に action に結果を書き込む必要はありません。

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
├── depth
├── branch_id
├── parent_state_ids
├── state_snapshot
├── assumptions
├── confidence
├── status
└── linked_transition_id
```

### state_snapshot

`state_snapshot` は、その node で agent が持っている状態です。

```text
state_snapshot
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
│ StateNode S2 depth=1 branch=launch_overhead   │
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
│  linked_transition_id: none                   │
└──────────────────────────────────────────────┘
```

ここに action の実行結果は入れません。
実行結果は `ActionResult`、矢印全体は `TransitionRecord` に置きます。

## ActionSpec

`ActionSpec` は、状態から選ばれる「これから何をするか」の仕様です。

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

`ActionSpec` は結果を持ちません。
実行後に `ActionSpec` を変更しません。

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

```text
TransitionRecord
├── transition_id
├── from_state_id
├── to_state_id
├── action_spec
├── action_result
├── observation
├── evidence
├── prediction_error
├── decision
├── finding
└── state_delta
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
       │  ├─ Evidence
       │  ├─ PredictionError
       │  ├─ Decision
       │  ├─ Finding
       │  └─ StateDelta
       v
┌──────────────┐
│ StateNode S7 │
└──────────────┘
```

`TransitionRecord` は、単なる action ではありません。
action の仕様、実行結果、観測、判断、学習、状態差分をまとめたものです。

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

```text
EvidenceTree

depth 0   [S0: observed baseline state]
             |
             | TransitionRecord T1
             | ActionSpec + ActionResult + Evidence
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

実行後は、`ActionResult` と `Evidence` が得られ、
`TransitionRecord` として EvidenceTree に記録されます。

```text
EvidenceTree

S0
 │
 │ TransitionRecord T7
 │  ActionSpec:
 │    implement fused dispatch
 │  ActionResult:
 │    patch, test logs, benchmark logs
 │  Evidence:
 │    small +18%, large -8%
 │  PredictionError:
 │    large was not neutral
 │  Decision:
 │    needs_narrower_scope
 │  Finding:
 │    useful only for small batch
 v
S7_observed
```

このとき、`ActionSpec` は変更しません。
実行結果は `ActionResult` に置き、予測との差分は `PredictionError` に置きます。

## 状態遷移の 1 step

1 step は以下のように表します。

```text
StateNode S_t
  -> choose ActionSpec
  -> execute ActionSpec
  -> produce ActionResult
  -> derive Observation
  -> normalize Evidence
  -> compare expected vs actual
  -> produce PredictionError
  -> decide
  -> learn Finding
  -> compute StateDelta
  -> create StateNode S_t+1
  -> append TransitionRecord
```

数式的には以下です。

```text
ActionSpec_t = policy(StateNode_t)
ActionResult_t = execute(ActionSpec_t)
Observation_t = observe(ActionResult_t)
Evidence_t = evaluate(Observation_t, requirement)
PredictionError_t = compare(ActionSpec_t.expected_observation, Observation_t)
Decision_t = decide(Evidence_t, promotion_policy)
Finding_t = learn(Evidence_t, PredictionError_t, Decision_t)
StateDelta_t = reduce(ActionResult_t, Evidence_t, Finding_t)
StateNode_t+1 = apply(StateNode_t, StateDelta_t)
TransitionRecord_t = record(
  StateNode_t,
  ActionSpec_t,
  ActionResult_t,
  Evidence_t,
  PredictionError_t,
  Decision_t,
  Finding_t,
  StateDelta_t,
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
5. `Evidence` は `Observation` から導出する。
6. `Decision` は `Evidence` と promotion policy から導出する。
7. `Finding` は次の action 選択に使える形で保存する。
8. `TransitionRecord` は append-only とする。
9. promotion と learning は分ける。
10. action 実行前に expected observation を持つ。
11. action 実行後に prediction error を評価する。
12. unsafe な試行は rejected ではなく `unsafe` として分ける。

## 保存形式

最初は JSON / JSONL を正とします。

```text
runs/<run_id>/
├── run.json
├── requirements.json
├── states.jsonl
├── transitions.jsonl
├── findings.jsonl
├── artifacts/
├── raw/
└── reports/
```

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
  矢印。ActionSpec、ActionResult、Evidence、Decision、Finding、StateDelta を束ねる。

PredictionTree:
  まだ実行していない future StateNode と PlannedTransition の tree。

EvidenceTree:
  実行済み StateNode と TransitionRecord の tree。
```

この形にすると、`State -> Action -> Result -> State` の反復推論を保ちながら、
action に実行結果を書き込む責務混在を避けられます。
