# 状態モデル

## 中心原則

optagent の状態モデルは、次の考え方を中心に置きます。

> 最適化は、不確実性のある状態から、予測を持った action によって次の状態へ進む過程である。

したがって、状態モデルは単なる履歴ではありません。
エージェントが今何を知っていて、何を信じていて、何が未解決で、
次に何を観測すべきかを表す必要があります。

## State と Evidence Graph を分ける

最初に重要なのは、`State` と `Evidence Graph` を分けることです。

```text
State
  現在の作業状態。
  次の action を選ぶために使う。

Evidence Graph
  過去の試行ログ。
  append-only で保存する。
```

`State` は現在の信念や候補を表すため、更新されます。
一方で `Evidence Graph` は過去の事実を表すため、基本的に変更しません。

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

## Evidence Graph

Evidence Graph は、run の履歴です。

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

## Attempt

`Attempt` は Evidence Graph の一つの node です。

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

Evidence Graph:
  過去の試行、観測、証拠、判断、学習

Transition:
  予測を持った action によって state がどう変わったか
```

この三つを分けることで、単なる反復 workflow ではなく、
未来を予測しながら調査、実装、検証、枝刈りを行う最適化エージェントを作れるようになります。
