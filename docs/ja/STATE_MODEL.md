# 状態モデル

## 中心原則

optagent の状態モデルは、次の考え方を中心に置きます。

> 最適化は、不確実性のある状態から、予測を持った action によって次の状態へ進む過程である。

したがって、状態モデルは単なる履歴ではありません。
エージェントが今何を知っていて、何を信じていて、何が未解決で、
次に何を観測すべきかを表す必要があります。

## State と Tree を分ける

最初に重要なのは、`State` と tree を分けることです。

```text
State
  現在の作業状態。
  次の action を選ぶために使う。

PredictionTree
  まだ実行していない未来予測。

EvidenceTree
  実際に実行した試行ログ。
  append-only で保存する。
```

`State` は現在の信念や候補を表すため、更新されます。
`PredictionTree` は未来の仮説的な状態を表すため、prune や merge されます。
`EvidenceTree` は過去の事実を表すため、基本的に変更せず append-only にします。

## State

`State` は、ある run の現在状態です。

```text
State
├── requirement
├── artifacts
├── knowledge
├── open_questions
├── active_branches
├── predictions
└── budget
```

### requirement

最適化対象と制約です。
run の途中で原則変更しません。

例:

```text
target_type: kernel
target_id: csc_linear_forward
objective: minimize latency
constraints: preserve correctness
promotion_policy: min_speedup >= 1.05
```

### artifacts

現在保持している候補です。

候補は一つとは限りません。
複数の candidate、incumbent、Pareto 的な候補集合を持つ可能性があります。

### knowledge

これまでに学んだことです。

例:

- small batch は launch overhead が支配的
- large shape では candidate A が regression する
- ある実装方針は numerical error を起こしやすい
- benchmark X だけでは promotion には不十分

### open_questions

まだ答えが出ていない問いです。

例:

- bottleneck は memory access か launch overhead か
- regression は shape-specific か
- correctness failure は indexing bug か numerical error か
- baseline は安定しているか

### active_branches

現在探索中の枝です。

例:

```text
branch A: launch overhead hypothesis
branch B: memory layout hypothesis
branch C: dispatch mismatch hypothesis
```

枝は evidence によって伸びたり、prune されたり、merge されたりします。

### predictions

今後こうなるはず、という予測です。

予測は action 実行前に作り、観測後にズレを評価します。

```text
expected:
  small shape improves
  large shape stays neutral

observed:
  small shape improves
  large shape regresses

prediction_error:
  candidate needs narrower scope
```

## Tree / Depth / Node

未来予測や実行履歴は、単なる node の集合ではなく、depth を持つ tree として扱います。

```text
Tree
├── depth 0
│   └── node: 現在状態
├── depth 1
│   ├── node: 次の action 候補 A
│   ├── node: 次の action 候補 B
│   └── node: 次の action 候補 C
├── depth 2
│   ├── node: A の後の候補 A1
│   ├── node: A の後の候補 A2
│   └── node: B の後の候補 B1
└── depth 3
    └── node: さらに先の候補
```

### なぜ depth を first-class にするか

最適化の推論では、node 単体だけでなく「同じ深さにある候補群」を比較することが重要です。

例えば depth 1 では、次に何を調べるか、何を実装するかを比較します。
depth 2 では、それぞれの action が成功した後に何が開けるかを比較します。
depth 3 では、複数の方針を組み合わせた未来を比較します。

```text
depth 0:
  現在の状態

depth 1:
  次に取れる action と、その直後の予測

depth 2:
  その action が成功/失敗した後に取れる次の action

depth 3:
  さらに組み合わせた場合の未来
```

したがって、データ構造としては以下を持ちます。

```text
Tree
├── depths: list[DepthLayer]
└── edges: list[TransitionEdge]

DepthLayer
├── depth
├── nodes
├── layer_summary
├── open_questions
└── comparison

Node
├── node_id
├── depth
├── parent_node_ids
├── branch_id
├── state_snapshot
├── state_delta
├── action
├── expected_observation
├── confidence
├── estimated_cost
├── status
└── linked_attempt_id
```

`DepthLayer` は、同じ階層の node を比較するための単位です。
agent が「この階層ではどの方向が有望か」を考えるときは、node 単体ではなく layer 全体を見ます。

### Node の中に State がある

各 node は、単なる action ではありません。
その node に到達したと仮定したときの state を持ちます。

```text
Node
└── state_snapshot
    ├── artifacts
    ├── knowledge
    ├── open_questions
    ├── active_branches
    └── predictions
```

これにより、同じ depth にある複数 node を「それぞれ別の未来状態」として比較できます。

### 遷移は一対一とは限らない

node 間の遷移は一対一である必要はありません。

```text
one-to-many:
  一つの状態から複数の未来候補へ分岐する

many-to-one:
  複数の枝が同じ説明や candidate に合流する

many-to-many:
  複数の前提から複数の候補が生まれる
```

したがって、tree と呼びつつも、内部表現としては edge を持つ graph に近くなる場合があります。
ただし、推論の主語はあくまで depth 付きの tree view です。

## PredictionTree

`PredictionTree` は、まだ実行していない未来予測です。

```text
PredictionTree
├── depth 0: current state
├── depth 1: next action candidates
├── depth 2: expected follow-up states
└── depth N: deeper forecast
```

PredictionTree の node は evidence ではありません。
あくまで予測です。

```text
PredictedNode
├── action
├── expected_observation
├── expected_state_delta
├── assumptions
├── confidence
├── estimated_cost
└── children
```

実際に action を実行したら、対応する predicted node は `Attempt` として
`EvidenceTree` に記録されます。

## EvidenceTree

`EvidenceTree` は、実際に実行した attempt の履歴です。

```text
Requirement
  -> Attempt
      -> Hypothesis
      -> Action
      -> Artifact
      -> Observation
      -> Evidence
      -> Decision
      -> Finding
```

これは append-only の log として保存します。

概念上は `EvidenceTree` と呼びます。
ただし、枝の merge や shared parent を厳密に表現する場合、内部実装は graph になっても構いません。
その場合でも、agent が読む view は depth を持つ EvidenceTree として提供します。

## Attempt

`Attempt` は EvidenceTree の一つの node です。

```text
Attempt
├── attempt_id
├── parent_attempt_id
├── branch_id
├── hypothesis
├── action
├── expected_observation
├── artifact
├── observation
├── evidence
├── decision
└── finding
```

### parent_attempt_id

どの試行から派生したかを示します。
これにより、探索の枝分かれを表現します。

### branch_id

同じ方向性を持つ試行をまとめる ID です。

例:

- `branch_launch_overhead`
- `branch_memory_layout`
- `branch_dispatch_scope`

### expected_observation

action 実行前の予測です。

これは非常に重要です。
予測がなければ、観測結果が「思った通り」なのか「意外」なのか判断できません。

### observation

action の生の観測結果です。

例:

- benchmark output
- test output
- profiler output
- trace log
- code inspection result

### evidence

observation を判断可能な形に正規化したものです。

例:

- correctness: passed
- speedup: 1.12
- regressions: batch_size=64
- eligible_scope: batch_size<=4

### decision

promotion や次の扱いに関する判断です。

canonical status:

- `accepted`
- `rejected`
- `needs_narrower_scope`
- `needs_more_evidence`
- `unsafe`

### finding

次の試行に使う知識です。

`Decision` は「この候補をどう扱うか」です。
`Finding` は「この試行から何を学んだか」です。

この二つは分けます。

## Action

Action は状態を変えるための単位です。

```text
Action
├── action_id
├── action_type
├── intent
├── expected_observation
├── estimated_cost
├── executor
└── safety_policy
```

### action_type

最低限、以下に分けます。

```text
InvestigationAction
ImplementationAction
VerificationAction
AnalysisAction
ScopeRefinementAction
```

### InvestigationAction

不確実性を減らすための action です。

例:

- profile workload
- run baseline matrix
- inspect dispatch
- read relevant code
- inspect failure log

### ImplementationAction

artifact を作る action です。

例:

- generate patch
- edit candidate kernel
- change dispatch condition
- create specialized implementation

### VerificationAction

正しさや性能を確認する action です。

例:

- run correctness tests
- run benchmark matrix
- compare numerical error
- run regression suite

### AnalysisAction

観測結果を説明する action です。

例:

- explain benchmark regression
- classify failure mode
- compare against prior findings

### ScopeRefinementAction

適用範囲を狭める action です。

例:

- restrict dispatch to small batch
- exclude dtype
- require specific shape family

## Transition

状態遷移は、action の予測と観測を比較して state を更新することです。

```text
Transition
├── state_before
├── action
├── expected_observation
├── observation
├── evidence
├── prediction_error
├── decision
├── finding
└── state_after
```

重要なのは `prediction_error` です。

予測と観測がズレたとき、それは失敗ではなく学習信号です。

## 遷移の全体像

optagent の 1 step は、次の流れで表します。

```text
State_t
  ├─ select action
  │    └─ Action_t
  │        ├─ intent
  │        ├─ expected_observation
  │        └─ estimated_state_delta
  │
  ├─ execute action
  │    └─ Observation_t
  │
  ├─ evaluate observation
  │    └─ Evidence_t
  │
  ├─ compare expected vs actual
  │    └─ PredictionError_t
  │
  ├─ decide
  │    └─ Decision_t
  │
  ├─ learn
  │    └─ Finding_t
  │
  └─ update state
       └─ State_t+1
```

数式的に書くと、以下です。

```text
Action_t = policy(State_t)
Observation_t = execute(Action_t)
Evidence_t = evaluate(Observation_t, State_t.requirement)
PredictionError_t = compare(Action_t.expected_observation, Observation_t)
Decision_t = decide(Evidence_t, State_t.requirement.promotion_policy)
Finding_t = learn(Evidence_t, PredictionError_t, Decision_t)
State_t+1 = update(State_t, Action_t, Evidence_t, Decision_t, Finding_t)
```

ここで重要なのは、`execute` 以外はすべて再実行可能であるべきという点です。
raw observation が保存されていれば、後から evaluator や promotion policy を変えて
再評価できます。

## 遷移の種類

すべての action は状態遷移を起こしますが、遷移の意味は action type によって違います。

### 1. 調査遷移

原因がわからないとき、不確実性を減らすための遷移です。

```text
State_t:
  open_questions:
    - bottleneck は launch overhead か memory access か

Action_t:
  type: InvestigationAction
  intent: profile workload by shape
  expected_observation:
    - small shape では launch overhead が支配的に見えるはず

Observation_t:
  profiler output

Evidence_t:
  small shape: launch overhead high
  large shape: memory bandwidth high

Finding_t:
  small と large で原因が違う可能性が高い

State_t+1:
  open_questions:
    - large shape の memory layout を調べる
  knowledge:
    - small shape は launch-bound
  active_branches:
    - branch_launch_overhead_small
    - branch_memory_layout_large
```

調査遷移では、candidate artifact が生まれないことがあります。
それでも、問いが減ったり branch が分かれたりすれば有効な遷移です。

### 2. 実装遷移

仮説に基づいて candidate artifact を作る遷移です。

```text
State_t:
  knowledge:
    - small shape は launch-bound

Action_t:
  type: ImplementationAction
  intent: implement fused dispatch for small shapes
  expected_observation:
    - small shape latency improves
    - large shape remains neutral

Artifact_t:
  patch: artifacts/attempt_0007.patch

Observation_t:
  test output
  benchmark matrix

Evidence_t:
  correctness: passed
  speedup_small: 1.18
  speedup_large: 0.92
  regressions:
    - batch_size=64

Decision_t:
  needs_narrower_scope

Finding_t:
  fused dispatch is promising only for small batch

State_t+1:
  artifacts:
    - candidate_0007 retained as scoped candidate
  knowledge:
    - do not promote this candidate for large batch
  active_branches:
    - branch_launch_overhead_small continues
    - large batch path pruned for this candidate
```

実装遷移では、artifact ができたこと自体よりも、
その artifact がどの条件で使えるかを明らかにすることが重要です。

### 3. 検証遷移

candidate を promotion できるか確認する遷移です。

```text
State_t:
  artifacts:
    - candidate_0007
  open_questions:
    - batch_size<=4 なら regression はないか

Action_t:
  type: VerificationAction
  intent: run narrowed benchmark matrix
  expected_observation:
    - batch_size<=4 では correctness passed
    - batch_size<=4 では speedup >= 1.05

Evidence_t:
  correctness: passed
  eligible_scope: batch_size<=4
  geometric_mean_speedup: 1.11
  regressions: []

Decision_t:
  accepted

Finding_t:
  candidate is promotable for small batch inference scope

State_t+1:
  artifacts:
    - candidate_0007 becomes incumbent for batch_size<=4
  open_questions:
    - removed narrowed-scope verification question
```

検証遷移は、新しい実装を作らないことがあります。
既存 candidate の証拠を厚くするための遷移です。

### 4. 分析遷移

予測と観測がズレたとき、その原因を説明するための遷移です。

```text
State_t:
  prediction_error:
    - expected large neutral, observed large regression

Action_t:
  type: AnalysisAction
  intent: explain large-shape regression
  expected_observation:
    - regression is caused by dispatch overhead or memory layout mismatch

Observation_t:
  benchmark breakdown
  code inspection notes

Finding_t:
  fused path adds overhead when compute dominates

State_t+1:
  knowledge:
    - avoid fused dispatch for compute-dominant large shapes
  active_branches:
    - branch_launch_overhead_small retained
    - branch_large_fused_dispatch pruned
```

分析遷移は、失敗を次の探索に使える知識へ変換するための遷移です。

### 5. 範囲調整遷移

candidate 自体は有望だが、適用範囲が広すぎるときの遷移です。

```text
State_t:
  decision:
    - needs_narrower_scope

Action_t:
  type: ScopeRefinementAction
  intent: restrict dispatch scope to batch_size<=4

Evidence_t:
  eligible_scope: batch_size<=4
  regressions outside scope: excluded

Decision_t:
  accepted or needs_more_evidence

State_t+1:
  artifacts:
    - candidate with narrowed dispatch policy
  knowledge:
    - scope constraint added
```

範囲調整遷移は、`rejected` と `accepted` の中間を扱うために重要です。
最適化では「全部には効かないが、条件付きなら使える」候補が多いためです。

## 状態更新の対象

`State_t+1` では、少なくとも以下が更新されます。

```text
State_t+1
├── artifacts
│   ├── candidate 追加
│   ├── incumbent 更新
│   └── scoped candidate 更新
├── knowledge
│   ├── finding 追加
│   ├── ruled-out region 追加
│   └── scope constraint 追加
├── open_questions
│   ├── 解決済み question を削除
│   └── 新しい question を追加
├── active_branches
│   ├── branch を伸ばす
│   ├── branch を prune する
│   └── branch を merge する
├── predictions
│   ├── 外れた予測を記録
│   └── 新しい予測を追加
└── budget
    └── action cost を差し引く
```

一方で、`EvidenceTree` には append-only で `Attempt` を追加します。

```text
EvidenceTree_t+1 = EvidenceTree_t + Attempt_t
```

つまり、`State` は現在の作業状態として更新され、
`EvidenceTree` は過去の事実として追記されます。

## 遷移の終了条件

run は次のいずれかで終了します。

- promotion 可能な candidate が見つかった
- budget が尽きた
- すべての有望 branch が prune された
- 追加 evidence が必要だが、現在の環境では取れない
- unsafe な兆候があり、人間の確認が必要になった
- 人間が十分と判断した

終了時にも `Finding` を残します。
成功だけでなく、「なぜこれ以上進めないか」も次回の重要な知識です。

## 不変条件

状態モデルには以下の不変条件を置きます。

1. `Requirement` は run の中で原則固定する。
2. `Attempt` は append-only とする。
3. raw `Observation` は保存する。
4. `Evidence` は `Observation` から導出する。
5. `Decision` は `Evidence` と promotion policy から導出する。
6. `Finding` は次の action 選択に使える形で保存する。
7. promotion と learning は分ける。
8. action 実行前に expected observation を持つ。
9. action 実行後に prediction error を評価する。
10. unsafe な試行は rejected ではなく `unsafe` として分ける。

## 保存形式

最初は JSON / JSONL を正とします。

```text
runs/<run_id>/
├── run.json
├── requirements.json
├── attempts.jsonl
├── decisions.jsonl
├── findings.jsonl
├── artifacts/
├── raw/
└── reports/
```

DB はまだ不要です。
まずは人間と agent が読める file contract を安定させます。

## まとめ

この状態モデルで重要なのは、以下の切り分けです。

```text
State:
  現在の信念、候補、問い、予測

PredictionTree:
  まだ実行していない、depth 付きの未来予測

EvidenceTree:
  過去の試行、観測、証拠、判断、学習

Transition:
  予測を持った action によって state がどう変わったか
```

この三つを分けることで、単なる反復 workflow ではなく、
未来を予測しながら調査、実装、検証、枝刈りを行う最適化エージェントを作れるようになります。
